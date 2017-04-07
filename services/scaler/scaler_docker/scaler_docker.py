# -*- coding: utf-8 -*-

import logging

from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.timer import timer

from components.dependency.docker import DockerClientProvider

logger = logging.getLogger(__name__)


class ScalerDocker(object):
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
    
    fetch_image_config(image_name: str): ScaleConfig
    scale(service_nane: str, n: int)
    get(service_name: str): list[Instance]
    
    """
    name = 'scaler_docker'
    dispatch = EventDispatcher()
    docker = DockerClientProvider()  # docker.client.DockerClient

    @timer(1)
    def lolilol(self):
        logger.debug("debug")

        from logging_tree import printout
        # printout()
        # raise Exception("lolilol")

    @timer(interval=4)
    def test(self):
        logger.debug("containers : %s", [c.name for c in self.docker.container.list()])


    @rpc
    def get(self, service_name):
        return [c.attrs for c in self.docker.container.list()]
