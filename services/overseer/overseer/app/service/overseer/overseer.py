# -*- coding: utf-8 -*-
import copy
import datetime
import logging
import pprint
from functools import partial

from common.db.mongo import Mongo
from common.entrypoint import once
from common.utils import ImageVersion, filter_dict, log_all, make_promise
from nameko.events import SERVICE_POOL, EventDispatcher, event_handler
from nameko.exceptions import UnknownService
from nameko.rpc import RpcProxy, rpc
from nameko.timer import timer
from promise.promise import Promise

logger = logging.getLogger(__name__)


class Overseer(object):
    """
    the main orchestation service. manages upgrades of services and propagate events for new version etc.

    public events
    #############

    - service_update(): Service

    subscribe
    #########

    - scaler.*[image_update]

    rcp
    ###

    deploy(image_type: str, image_name: str)
    list_service(): list[Service]
    update_metric(metric, value)

    """
    name = 'overseer'
    dispatch = EventDispatcher()
    scaler_docker = RpcProxy("scaler_docker")
    """
    :type: service.scaler_docker.scaler_docker.ScalerDocker
    """
    trigger = RpcProxy('trigger')
    """
    :type: service.trigger.trigger.Trigger
    """
    mongo = Mongo(name)
    """
    :type: mongo.Mongo
    """

    type_to_scaler = {
        "docker": "scaler_docker",
    }
    reversed_type_to_scaler = {b: a for a, b in type_to_scaler.items()}

    # ####################################################
    #                 EVENTS
    # ####################################################

    @event_handler(
        "scaler_docker", "service_updated", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def on_service_updated(self, payload):
        logger.debug("notified service updated with %s", payload)
        service_data = payload['service']
        service = self._get_service(service_data['name'])
        diff = self._compute_diff(service_data, service)
        scaler = self._get_scaler(service)
        self._save_service_state(service_data, scaler, service)
        if diff:
            self.dispatch('service_updated', {"service": filter_dict(service), "diff": diff})

    @event_handler(
        "overseer", "service_updated", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def check_new_scaler_config(self, payload):
        """
        check if the image is changed, this mean a new scaler-config is changed too ?
        :param dict payload: the payload sent by self.on_service_updated
        :return:
        """
        diff = payload['diff']
        if diff.get('image'):
            image_version = ImageVersion.deserialize(diff['image']['to'])
            scale_config = self.scaler_docker.fetch_image_config(image_version.unique_image_id)
            service_ = payload['service']
            if service_['scale_config'] != scale_config:
                self.mongo.services.update_one(
                    {'name': service_['name']},
                    {'$set': {
                        "scale_config": scale_config,
                    }}
                )
                diff = {
                    "scale_config": {'from': copy.deepcopy(service_['scale_config']), 'to': scale_config},
                }
                service_['scale_config'] = scale_config
                self.dispatch('service_updated', {
                    'service': service_,
                    'diff': diff,
                })

    @event_handler(
        "scaler_docker", "image_updated", handler_type=SERVICE_POOL, reliable_delivery=False
    )
    @log_all
    def on_image_updated(self, payload):
        """
        each time an image is updated
        :param payload: the event data, must contains :
            - from: the name of the service (ie: scaler_docker)
            - image_name: the name of the image
            - image_id: the uniq identifier for this image, send back to the scaler if the upgrade is validated
            - [O]version : displayed version
            - [O]digest: the digest for this image
        """
        scaler_type = self.reversed_type_to_scaler[payload['from']]
        assert scaler_type == 'docker'
        if set(payload) < {'repository', 'image', 'tag', 'digest'}:
            return  # update can be called with blob update instead of images

        new_image_version = ImageVersion.from_scaler(payload)
        logger.debug("version found for this push : %s", new_image_version)

        for service in self._get_services(scaler_type=scaler_type, full_image_id=new_image_version.image_id):
            current_image_version = ImageVersion.deserialize(service['image']['image_info'])
            logger.debug("current image: %s new one : %s", current_image_version, new_image_version)
            if current_image_version == new_image_version:
                continue

            # TODO: change behavior and use dependency

    # ####################################################
    #                 ONCE
    # ####################################################

    @once
    @log_all
    def fetch_services(self):
        if not self.mongo.services.find_one():
            for scaler in self._get_scalers():
                result = scaler.list_services()
                for service in result:
                    if 'rabbitmq' not in service['name']:
                        self.monitor(scaler.type, service['name'])
        logger.debug("services: %s", pprint.pformat(list(self.mongo.services.find()), indent=2, width=119))

    # ####################################################
    #                 RPC
    # ####################################################

    @rpc
    def deploy(self, service):
        """
        create a service on the valide scaler
        :param service:
        :return:
        """
        logger.debug("ask for update %s", service)

    @rpc
    @log_all
    def monitor(self, scaler_name, service_name):
        """
        attache a running service from the given scaler to the monitoring services.
        :param scaler_name: the name of the scaler (must be registered befor)
        :param service_name: the name of the service
        :return:
        """
        existing_service = self.get_service(service_name)
        if existing_service:
            logger.info("ask for monitoring an already registered service  update it%s" % service_name)

        scaler = self._get_scaler(scaler_name)
        service_data = scaler.get(service_name=service_name)
        config = scaler.fetch_image_config(service_data['full_image_id'])
        image_version = ImageVersion.from_scaler(service_data)
        result = {
            "name": service_name,
            "image": {
                "type": scaler.type,
                "image_info": image_version.serialize(),
                'full_image_id': image_version.image_id,
            },
            "scale_config": config,
            "start_conig": {
                "env": service_data.get('env', {}),
                "secret": [],
            },
            "latest_ruleset": {},
            "mode": service_data['mode']
        }
        self.mongo.services.update(
            {'name': service_name},
            result,
            upsert=True,
        )

    @rpc
    def list_service(self):
        """
        list all registered services with their metadata
        :return:
        """
        return [filter_dict(s) for s in self.mongo.services.find()]

    @rpc
    @log_all
    def get_service(self, service_name):
        """
        return all current state for the given service.
        :param service_name: the service's name
        :return: all internal data from db
        """

        service = self._get_service(service_name)
        return service and filter_dict(service)

    @rpc
    @log_all
    def unmonitor_service(self, service_name):
        """
        return all current state for the given service.
        :param service_name: the service's name
        :return: all internal data from db
        """

        return self._remove_service(service_name)

    @rpc
    @log_all
    def test(self):
        s = self._get_services('docker', full_image_id='nginx')
        return [filter_dict(d) for d in s]

    @rpc
    @log_all
    def scale(self, service_name, scale):
        """
        scale the given service by his name to the given amount of instances.
        :param str service_name:  the name of the service
        :param int scale:  the number of instance required (don't check anything)
        :return:
        """
        logger.debug("scaling service %s to %s", service_name, scale)
        service = self.get_service(service_name)
        self._update_service(service, scale=scale)


    @rpc
    @log_all
    def reload_from_scaler(self, service_name):
        """
        reload all available metric/config from the scaler for a given service.
        :param service_name: the service's name
        :return: the new service config
        """
        service = self._get_service(service_name)
        logger.debug("rechargement depuis le scaler: %s", service_name)
        if service is None:
            raise UnknownService(service_name)
        # update scaler config
        scaler = self._get_scaler(service)
        current_image_version = ImageVersion.deserialize(service['image']['image_info'])

        update_scale_config = make_promise(
            scaler.fetch_image_config.call_async(current_image_version.unique_image_id)
        ).then(
            partial(self.__update_scale_config, service=service)
        )

        update_service = make_promise(
            scaler.get.call_async(service_name)
        ).then(
            partial(self._save_service_state, scaler=scaler, service=service)
        )
        Promise.all([update_scale_config, update_service]).get()

        return filter_dict(service)

    # #######################################################
    #                    PRIVATE FUNCTIONS
    # #######################################################

    @log_all
    def _get_scaler(self, scaler):
        if isinstance(scaler, dict):
            # we get a service
            scaler_name = scaler['image']['type']
        else:
            scaler_name = scaler
        assert scaler_name == 'docker', "we only support scaler <docker>. %s was asked" % scaler_name
        self.scaler_docker.type = 'docker'
        return self.scaler_docker

    def _get_scalers(self):
        self.scaler_docker.type = 'docker'
        return self.scaler_docker,  # tuple

    def _get_service(self, service_name):
        return self.mongo.services.find_one({'name': service_name})

    def _remove_service(self, service_name):
        return self.mongo.services.remove({'name': service_name})

    def _get_services(self, scaler_type, full_image_id=None):
        q = {
            "$and": [
                {'image.type': scaler_type},
                {'image.full_image_id': full_image_id},
            ]
        }
        return self.mongo.services.find(q)

    def _update_service(self, service, **kwargs):
        """
        ask the scaler to update a service with folowing params:
        - mode
        - image
        :param kwargs:
        :rtype: Promise
        """
        promise = make_promise(self._get_scaler(service).update.call_async(
            service_name=service['name'],
            **kwargs
        ))

        return promise.then(lambda osef: self.reload_from_scaler(service_name=service['name']))

    # ###################################################################
    #                       common method
    # ###################################################################

    def _save_service_state(self, service_data, scaler, service):
        """
        update thee given service in base and in-memory with service_data
        :param service:
        :return:
        """
        # update replicas current status
        service['mode'] = service_data['mode']
        imageversion = ImageVersion.from_scaler(service_data)
        service['image'] = {
            "type": scaler.type,
            "image_info": imageversion.serialize(),
            'full_image_id': imageversion.image_id
        }
        self.mongo.services.update_one(
            {'_id': service['_id']},
            {'$set': {
                "mode": service['mode'],
                "image": service['image'],
            }}
        )

    def _compute_diff(self, service_data, service):
        """
        return a dict with the diff between the old state and the new state of a service.
        currently check: scale, images, scale_config, env.
        {"change item": {"from": oldval, "to": newval}}
        :param service_data: the data of the service from the changed event
        :param service: the service as saved in the database befor the change.
        :return: the dict with the changes. in form: {'from': ..., 'to': ...} with the folowing parts:

            - scale: the number of instances
            - mode: the mode if changes (name + replicas)
            - image: the imageversion serialized if changed

        """
        changes = {}
        if service_data['mode'] != service['mode']:
            if service_data['mode']['name'] == "replicated" and service['mode']['name'] == "replicated":
                changes['scale'] = {'from': service['mode']['replicas'], 'to': service_data['mode']['replicas']}
            else:
                changes['mode'] = {'from': service['mode'], 'to': service_data['mode']}
        img_version_serialized = ImageVersion.from_scaler(service_data).serialize()
        if img_version_serialized != service['image']['image_info']:
            changes['image'] = {'from': service['image']['image_info'], 'to': img_version_serialized}
        return changes

    def __update_scale_config(self, new_scale_config, service):
        scale_config = service.get('scale_config') or {}
        logger.debug("get scaler %s fetch config for %s", service['image']['type'], service['image']['full_image_id'])
        new_scale_config = new_scale_config or self._get_scaler(service['image']['type']).fetch_image_config(
            service['image']['full_image_id'])
        logger.debug("old new %s \n\n========\n%s", scale_config, new_scale_config)

        if scale_config != new_scale_config:
            # the scale config has been updated
            service['scale_config'] = new_scale_config
            self.mongo.services.update_one({'_id': service['_id']}, {'$set': {"scale_config": new_scale_config}})
            self._set_trigger_rules(service)
            logger.debug("updated scale config for %s" % service['name'])
