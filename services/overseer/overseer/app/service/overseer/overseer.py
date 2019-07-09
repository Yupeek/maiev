# -*- coding: utf-8 -*-
import copy
import logging
import pprint
import time

from nameko.events import SERVICE_POOL, EventDispatcher, event_handler
from nameko.exceptions import RemoteError, UnknownService
from nameko.rpc import RpcProxy, rpc
from nameko.timer import timer
from promise.promise import Promise

from common.base import BaseWorkerService
from common.db.mongo import Mongo
from common.entrypoint import once
from common.utils import ImageVersion, filter_dict, log_all, make_promise

logger = logging.getLogger(__name__)


class NotMonitoredServiceException(Exception):
    pass


class Overseer(BaseWorkerService):
    """
    the main orchestation service. manages upgrades of services and propagate events for new version etc.

    public events
    #############

    - service_update(): Service

    subscribe
    #########

    - scaler.*[image_update]

    rpc
    ###

    deploy(image_type: str, image_name: str)
    list_service(): list[Service]
    update_metric(metric, value)

    """
    name = 'overseer'
    scaler_docker = RpcProxy("scaler_docker")
    """
    :type: service.scaler_docker.scaler_docker.ScalerDocker
    """
    load_manager = RpcProxy('overseer_load_manager')
    """
    :type: service.load_manager.load_manager.LoadManager
    """
    mongo = Mongo(name)
    """
    :type: mongo.MongoClient

    collections
    ***********

    services
    ########
    list of all services managed by overseer::

        name: producer
        image:
          type: docker
          image_info: # ImageVersion.serialize
            repository: localhost:5000
            image: maiev
            tag: producer-1.0.16
            species: producer
            version: 1.0.16
            digest: sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b
          full_image_id: localhost:5000/maiev:producer
        scale_config:  # content of scale_info

        mode:
          name: replicated
          replicas: 23

    versions
    ########

    store history of all version available in registry.
    it's used to emit «new_version» or «unavailable_version»

    his format is exactly what ImageVersion.serialize output::

        repository: localhost:5000
        image: maiev
        tag: producer-1.0.16
        species: producer
        version: 1.0.16
        digest: sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b

    """

    dispatch = EventDispatcher()
    """
    events
    ******

    service_updated
    ###############

    dispatched each time a service is updated. either his image or his replicas count.

    payload: content of the service and the computed diff between old and new states.::

        service:
          name: producer
          image:
            type: docker
            image_info: # ImageVersion.serializ
              repository: localhost:5000
              image: maiev
              tag: producer-1.0.16
              species: producer
              version: 1.0.16
              digest: sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b
            full_image_id: localhost:5000/maiev:producer
          scale_config:  # content of scale_info
          mode:
            name: replicated
            replicas: 23
        diff:
          image: # facultatif
            from: #image_info
            to: #image_info
          replicas: # facultatif
            from:
              name: replicated
              replicas: 2
            to:
              name: global
          scale: # facultatif
            from: 2
            to: 3

    new_image
    #########

    emmited each timeea new image is detected on the targeted registry

    payload::

        service:  # all current data of the service
          name: producer
          image:
            type: docker
            image_info: # ImageVersion.serializ
              repository: localhost:5000
              image: maiev
              tag: producer-1.0.16
              species: producer
              version: 1.0.16
              digest: sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b
            full_image_id: localhost:5000/maiev:producer
          scale_config:  # content of scale_info
          mode:
            name: replicated
            replicas: 23
        image:  # ImageVersion data of the new image
          repository: localhost:5000
          image: maiev
          tag: producer-1.0.17
          species: producer
          version: 1.0.17
          digest: sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b
        scale_config: scale_config

    """

    type_to_scaler = {
        "docker": "scaler_docker",
    }
    reversed_type_to_scaler = {b: a for a, b in type_to_scaler.items()}

    # ####################################################
    #                 TIMER
    # ####################################################

    @once
    @timer(interval=60 * 30)  # every 30 minutes
    @rpc
    @log_all
    def recheck_new_version(self):
        """
        check in a new version is present for each managed services.
        it's a fallback if we missed the notification of the registry.

        :return:
        """
        images = {}

        # first, we get all images used by services.
        # many services can use same image. so we aggregates them
        for service in self._get_services(scaler_type='docker'):
            k = "{repository}/{image}".format(**service['image']['image_info'])
            images.setdefault(k, []).append(service)

        logger.debug("images and services to check : %s", {k: [i['name'] for i in v] for k, v in images.items()})
        # we start by checking each images
        for image, services in images.items():

            repository_tags = set(self.scaler_docker.list_tags(image))

            image_info = services[0]['image']['image_info']
            query = {
                "repository": image_info['repository'],
                "image": image_info['image']
            }
            versions = {v['tag']: ImageVersion.deserialize(v) for v in self.mongo.versions.find(query)}
            """:type dict[str, ImageVersion]"""
            existing_tags = set(versions)
            for missing_tag in existing_tags - repository_tags:
                removed_version = versions[missing_tag]
                # we notify all services using this images
                for service in services:
                    # do this service (which use this image) use this spacie too ?
                    if service['image']['full_image_id'] != removed_version.image_id:
                        continue
                    logger.info("detected %s image removed %s: %s", service['name'], missing_tag, removed_version)
                    self.dispatch('cleaned_image', {'service': filter_dict(service),
                                                    'image': filter_dict(removed_version.serialize())})
                    self.mongo.versions.remove({'_id': removed_version.data['_id']})

            for new_tag in repository_tags - existing_tags:
                constructed_version = ImageVersion.from_scaler({
                    "repository": image_info['repository'],
                    "image": image_info['image'],
                    "tag": new_tag,
                })
                for service in services:
                    # do this service (which use this image) use this spacie too ?
                    if service['image']['full_image_id'] != constructed_version.image_id:
                        continue
                    logger.info("detected %s new image %s: %s", service['name'], new_tag, constructed_version)
                    self._notify_new_image('docker', constructed_version)

    # ####################################################
    #                 EVENT
    # ####################################################

    @event_handler(
        "scaler_docker", "service_updated", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def on_service_updated(self, payload):
        """
        update the state of the updated service and dispatch service_ùpdated
        :param payload:
        :return:
        """
        logger.debug("notified service updated with %s", payload)
        service_data = payload['service']
        attributes = payload.get('attributes', {})
        service = self._get_service(service_data['name'])
        if service is None:
            logger.warning("detected service «%s» updated which is not monitored : %s", service_data['name'], payload)
            return
        diff = self._compute_diff(service_data, service, attributes)
        scaler = self._get_scaler(service)
        self._save_service_state(service_data, scaler, service)
        logger.debug("found diff for this update: %s", diff)
        if diff:
            logger.debug("dispatching service_updated: %s", filter_dict(service))
            self.dispatch('service_updated', {"service": filter_dict(service), "diff": diff})

    @event_handler(
        "overseer", "service_updated", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def check_new_scale_config(self, payload):
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
        each time an image is uploaded into a registry and the registry triggered us
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

        image_version = ImageVersion.from_scaler(payload)
        self._notify_new_image(scaler_type, image_version)

    # ####################################################
    #                 ONCE
    # ####################################################

    @once
    @log_all
    def fetch_services(self):
        time.sleep(4)
        if not self.mongo.services.find_one():
            for scaler in self._get_scalers():
                result = scaler.list_services()
                for service in result:
                    try:
                        # we check if the service contains required config
                        scale_config = self.scaler_docker.fetch_image_config(service['full_image_id'])
                    except RemoteError:
                        pass
                    else:
                        if scale_config:
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
            "start_config": {
                "env": service_data.get('env', {}),
                "secret": [],
            },
            "mode": service_data['mode']
        }
        self.mongo.services.update(
            {'name': service_name},
            result,
            upsert=True,
        )
        try:
            self.load_manager.monitor_service.call_async(result)
        except UnknownService:
            logger.error("no load_manager running to catch monitoring request for %s. you can re-call monitor(%s) "
                         "later to fix it", service_name, service_name)
        self.dispatch('service_updated', {"service": filter_dict(result), "diff": {}})

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
        s = self._get_services('docker', full_image_id='localhost:5000/maiev:producer')
        return [filter_dict(d) for d in s]

    @rpc
    @log_all(NotMonitoredServiceException)
    def scale(self, service_name, scale):
        """
        scale the given service by his name to the given amount of instances.
        :param str service_name:  the name of the service
        :param int scale:  the number of instance required (don't check anything)
        :return:
        """
        logger.debug("scaling service %s to %s", service_name, scale)
        service = self.get_service(service_name)
        logger.debug("scaling service: %s", service)
        if service is None:
            raise NotMonitoredServiceException("service %s is not monitored by overseer" % service_name)
        self._update_service(service, scale=scale)

    @rpc
    @log_all
    def upgrade_service(self, service_name, image_id):
        if isinstance(image_id, dict):
            image_id = ImageVersion.deserialize(image_id).unique_image_id
        service = self.get_service(service_name)
        if service is None:
            raise NotMonitoredServiceException("service %s is not monitored by overseer" % service_name)
        self._update_service(service, image_id=image_id)

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

    def _get_services(self, scaler_type=None, full_image_id=None):
        _and = []
        if scaler_type:
            _and.append({'image.type': scaler_type})
        if full_image_id:
            _and.append({'image.full_image_id': full_image_id})
        q = {
            "$and": _and
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
        self._get_scaler(service).update.call_async(
            service_name=service['name'],
            **kwargs
        )

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

    def _compute_diff(self, service_data, service, attributes):
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

        img_version_serialized = ImageVersion.from_scaler(service_data).serialize()
        if service is None:
            changes['mode'] = {'from': None, 'to': service_data['mode']}
            changes['image'] = {'from': None, 'to': img_version_serialized}
        else:
            try:
                if service_data['mode'] != service['mode']:
                    if service_data['mode']['name'] == "replicated" and service['mode']['name'] == "replicated":
                        changes['scale'] = {'from': service['mode']['replicas'],
                                            'to': service_data['mode']['replicas']}
                    else:
                        changes['mode'] = {'from': service['mode'], 'to': service_data['mode']}
            except KeyError:
                pass

            try:
                if img_version_serialized != service['image']['image_info']:
                    changes['image'] = {'from': service['image']['image_info'], 'to': img_version_serialized}
            except KeyError:
                pass
        if 'updatestate.new' in attributes:
            changes['state'] = {'from': attributes.get('updatestate.old'), 'to': attributes['updatestate.new']}

        return changes

    def _notify_new_image(self, scaler_type, image_version):
        """
        check if this new version is meaningfull for our cluster and dispatch «new_image» event in this case.
        :param scaler_type:
        :param image_version:
        :return:
        """
        logger.debug("version found for this push : %s. searching for %s", image_version, image_version.image_id)

        for service in self._get_services(scaler_type=scaler_type, full_image_id=image_version.image_id):
            logger.debug("getting image config for %s", image_version.unique_image_id)
            scale_config = self.scaler_docker.fetch_image_config(image_version.unique_image_id)
            logger.debug("will dispatch new event for service %s", service['name'])
            self.dispatch("new_image", {
                "service": filter_dict(service),
                "image": image_version.serialize(),
                "scale_config": scale_config
            })
            self.mongo.versions.insert(image_version.serialize())
