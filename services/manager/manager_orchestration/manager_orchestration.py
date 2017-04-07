# -*- coding: utf-8 -*-

import logging

from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.timer import timer

logger = logging.getLogger(__name__)


class ManagerOrchestration(object):
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
    name = 'manager_orchestration'
    dispatch = EventDispatcher()


    @timer(interval=4)
    def test(self):
        logger.debug("coucou")

    @rpc
    def deploy(self, service):
        logger.debug("ask for update %s", service)

    @rpc
    def list_service(self, service):
        return []
