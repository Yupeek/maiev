# -*- coding: utf-8 -*-

import logging

from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.timer import timer

logger = logging.getLogger(__name__)


class ManagerOrchestration(object):
    """
    the docker swarm adapter
    
    emited event
    ############
    
    - image_updated(): ScaleConfig 
     
    subscribe
    #########
    
    None
    
    rcp
    ###
    
    fetch_image_conig(image_name: str): ScaleConfig
    scale(service_nane: str, n: int)
    get(service_name: str): list[Instance]
    
    """
    name = 'manager_orchestration'
    dispatch = EventDispatcher()


    @timer(interval=4)
    def test(self):
        logger.debug("coucou")

