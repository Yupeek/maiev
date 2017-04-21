# -*- coding: utf-8 -*-
import logging

import eventlet
import itertools
from nameko.rpc import RpcProxy
from nameko.timer import timer

from common.entrypoint import once

logger = logging.getLogger(__name__)


class Consumer(object):
    """
    the monitorer that track rabbitmq stats to 
    report performance issues
    
    public events
    #############
    
    - metric_updated(): Service
    
    rcp
    ###
    
    track(identifier)
    
    """
    name = 'consumer'
    producer = RpcProxy('producer')
    """
    :type: producer.Producer
    """

    # ####################################################
    #                 EVENTS
    # ####################################################

    # no events

    # ####################################################
    #                 ONCE
    # ####################################################

    # ####################################################
    #                 RPC
    # ####################################################

    @once
    def start(self):
        count = 0
        tot = 0
        maxi = 5000
        while tot < maxi:
            with eventlet.Timeout(1, exception=False):
                for count in itertools.count():
                    if count + tot > maxi:
                        break
                    res = self.producer.get.call_async()

            tot += count
            logger.debug("{} calls/s".format(count))

