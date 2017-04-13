# -*- coding: utf-8 -*-

import logging

from nameko.events import EventDispatcher, SERVICE_POOL, event_handler
from nameko.rpc import rpc, RpcProxy

from common.utils import log_all, once

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
    services = [

    ]

    type_to_scaler = {
        "docker": "scaler_docker",
    }
    reversed_type_to_scaler = {b:a for a,b in type_to_scaler.items()}

    @event_handler(
        "scaler_docker", "image_updated", handler_type=SERVICE_POOL, reliable_delivery=False
    )
    @log_all
    def on_image_update(self, payload):
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
        service = self.get_service(scaler_type=scaler_type, image_name=payload['image_name'])
        logger.debug("updating %s", service)
        if service:
            self.scaler_docker.upgrade.call_async(
                service_name=service['service_name'],
                image_id=payload['image_id']
            )

    @once
    @log_all
    def fetch_services(self):
        services = []
        result = self.scaler_docker.list_services()
        for service in result:
            services.append({
                "service_name": service['name'],
                "image_name": service['image'],
                "type": "docker",
            })
        self.services[:] = services
        logger.debug("services actual : %s", self.services)

    @rpc
    def deploy(self, service):
        logger.debug("ask for update %s", service)

    @rpc
    def list_service(self, service):
        return []

    def get_service(self, scaler_type, service_name=None, image_name=None):
        for service in self.services:
            if service['type'] == scaler_type and (
                            service_name == service['service_name'] or image_name == service['image_name']):
                    return service
