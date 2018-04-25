# -*- coding: utf-8 -*-
import logging

from common.utils import log_all
from nameko.rpc import rpc
import nameko.cli.main

logger = logging.getLogger(__name__)


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
        # eventlet.patcher.original('time').sleep(0.009)
        return 42

    @rpc
    @log_all
    def echo(self, *args, **kwargs):
        logger.debug("got echo for args=%r      kwargs=%r", args, kwargs)
        return {
            "args": args,
            "kwargs": kwargs
        }

    @rpc
    @log_all
    def raises(self, message):
        raise Exception(message)