# -*- coding: utf-8 -*-
import logging

from nameko.extensions import DependencyProvider
from nameko.rpc import rpc
import eventlet.patcher
logger = logging.getLogger(__name__)


class LocalVal(DependencyProvider):

    def __init__(self, default=0.5):
        self.val = {
            'sleeptime': default,
            'current': default*2,
        }

    def get_dependency(self, worker_ctx):
        return self.val


class Producer(object):
    """
    a fake service that produce data in a specified time
    used to test service auto scale
    
    public events
    #############
    
    rcp
    ###
    
    set(rate)
    
    get()
    
    """
    name = 'producer'
    sleep = LocalVal(0.01)  # type: dict

    # ####################################################
    #                 EVENTS
    # ####################################################

    # no events

    # ####################################################
    #                 ONCE
    # ####################################################

    # no once

    # ####################################################
    #                 RPC
    # ####################################################

    @rpc
    def get(self):
        """
        create a service on the valide scaler
        :param service: 
        :return: 
        """
        eventlet.patcher.original('time').sleep(0.009)
        return 42
