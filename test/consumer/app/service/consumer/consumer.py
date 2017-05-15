# -*- coding: utf-8 -*-
import logging

import eventlet
import itertools

from common.dependency import PoolProvider
from common.utils import log_all
from nameko.rpc import RpcProxy

from common.entrypoint import once
from nameko.web.handlers import http

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
    pool = PoolProvider()
    """
    :type: eventlet.greenpool.GreenPool
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
    @log_all
    def start(self):
        logger.debug("starting query ")
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

    @http('GET', '/')
    @log_all
    def trigger(self, request):
        self.pool.spawn(self.start)
        return '<html><body><h3>started 5000 queries to Consumer</h3></body></html>'
