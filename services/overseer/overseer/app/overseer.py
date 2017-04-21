# -*- coding: utf-8 -*-
import json
import logging
import pprint
from functools import partial

from nameko.events import EventDispatcher, SERVICE_POOL, event_handler
from nameko.rpc import rpc, RpcProxy
from promise.promise import Promise

from common.db.mongo import Mongo
from common.utils import log_all, filter_dict, merge_dict, make_promise, then
from common.entrypoint import once

logger = logging.getLogger(__name__)


class Overseer(object):
    """
    the main orchestation service
    
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
    :type: scaler_docker.ScalerDocker
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
        "scaler_docker", "service_updated", handler_type=SERVICE_POOL, reliable_delivery=False
    )
    @log_all
    def on_service_updated(self, payload):
        logger.debug("notified service updated with %s", payload)
        service_data = payload['service']
        service = self._get_service(service_data['name'])
        scaler = self._get_scaler(service)
        self.__update_service_data(service_data, scaler, service)

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
        logger.debug("received image update notification %s", payload)
        scaler_type = self.reversed_type_to_scaler[payload['from']]
        assert scaler_type == 'docker'

        for service in self._get_services(scaler_type=scaler_type, image_name=payload['image_name']):
            logger.debug("check for updating %s", service['name'])
            logger.debug("current image: %s new one : %s", service.get('image', {}).get("full_image_id") , payload['full_image_id'] )
            if service.get('image', {}).get("full_image_id") == payload['full_image_id']:
                logger.debug("service %s already with the notified image", service['name'])
                continue

            new_scale_config = payload['scale_config']
            scale_config = service.get('scale_config') or {}
            if new_scale_config:
                merged = merge_dict(scale_config, new_scale_config)
                if merged:
                    service['scale_config'] = scale_config
                    # the scale config has been updated
                    self.mongo.services.update_one({'_id': service['_id']}, {'$set': {"scale_config": scale_config}})

            if scale_config.get('auto_update', True):
                new_scale_size = self._get_best_scale(service)
                extra_args = dict(
                    image_id=payload['full_image_id']
                )
                if new_scale_size is not None:
                    extra_args['scale'] = new_scale_size
                logger.debug("updating %s with %s", service['name'], extra_args)
                self._update_service(service, **extra_args)

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
                    self.monitor(scaler.type, service['name'])
        logger.debug("services: %s", pprint.pformat(list(self.mongo.services.find()), indent=2))

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
            logger.error("ask for monitoring an already registered service %s" % service_name)

        scaler = self._get_scaler(scaler_name)
        service_data = scaler.get(service_name=service_name)
        config = scaler.fetch_image_config(service_data['full_image_id'])
        result = {
            "name": service_name,
            "image": {
                "type": scaler.type,
                "name": service_data['image'],
                "repository": service_data['repository'],
                "version": service_data['version'],
                'full_image_id': service_data['full_image_id'],
            },
            "scale_config": config,
            "start_conig": {
                "env": service_data.get('env', {}),
                "secret": [],
            },
            "mode": service_data['mode']
        }
        self.mongo.services.insert_one(result)
        logger.debug("inserted service %s: \n%s", service_name, result)

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
    def test(self):
        s = self._get_services('docker', image_name='nginx')
        return [filter_dict(d) for d in s]

    @rpc
    @log_all
    def get_best_scale(self, service_name):
        return self._get_best_scale(self._get_service(service_name))

    @rpc
    @log_all
    def reload_from_scaler(self, service_name):
        """
        reload all available metric/config from the scaler for a given service.
        :param service_name: the service's name
        :return: the new service config
        """
        service = self._get_service(service_name)
        # update scaler config
        scaler = self._get_scaler(service)

        update_scale_config = make_promise(scaler.fetch_image_config.call_async(service['image'])).then(
            partial(self.__update_scale_config, service=service)
        )

        update_service = make_promise(scaler.get.call_async(service_name)).then(
            partial(self.__update_service_data, scaler=scaler, service=service))

        Promise.all([update_scale_config, update_service]).get()
        return filter_dict(service)

    # #######################################################
    #                    PRIVATE FUNCTIONS
    # #######################################################

    def _get_scaler(self, scaler):
        if isinstance(scaler, dict):
            # we get a service
            scaler_name = scaler['image']['type']
        else:
            scaler_name = scaler
        assert scaler_name == 'docker'
        self.scaler_docker.type = 'docker'
        return self.scaler_docker

    def _get_scalers(self):
        self.scaler_docker.type = 'docker'
        return self.scaler_docker,  # tuple

    def _get_service(self, service_name):
        return self.mongo.services.find_one({'name': service_name})

    def _get_services(self, scaler_type, image_name=None):
        q = {
            "$and": [
                {'image.type': scaler_type},
                {'image.name': image_name},
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

        return promise

    def _get_best_scale(self, service):
        """

        :param service: 
        :return: 
        """
        mode = service.get('mode', {'name': 'replicated', 'replicas': 1})
        scale_config = service.get('scale_config') or {}

        if mode['name'] == 'replicated':
            current = mode['replicas']
            best = current
            # TODO: compute for load here
            # respect max/min from scale_config
            best = max((best, scale_config.get('min', 0)))
            best = min((best, scale_config.get('max', best)))
            return best

    # ###################################################################
    #                       common method
    # ###################################################################

    def __update_service_data(self, service_data, scaler, service):
        """
        update thee given service in base and in-memory with service_data
        :param service: 
        :return: 
        """
        # update replicas current status
        service['mode'] = service_data['mode']
        service['image'] = {
            "type": scaler.type,
            "name": service_data['image'],
            "repository": service_data['repository'],
            "version": service_data['version'],
            'full_image_id': service_data['full_image_id'],
        }
        self.mongo.services.update_one(
            {'_id': service['_id']},
            {'$set': {
                "mode": service['mode'],
                "image": service['image'],
            }}
        )

    def __update_scale_config(self, new_scale_config, service):
        scale_config = service.get('scale_config') or {}
        if new_scale_config:
            merged = merge_dict(scale_config, new_scale_config)
            if merged:
                # the scale config has been updated
                service['scale_config'] = scale_config
                self.mongo.services.update_one({'_id': service['_id']}, {'$set': {"scale_config": scale_config}})