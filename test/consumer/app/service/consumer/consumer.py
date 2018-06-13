# -*- coding: utf-8 -*-
import datetime
import itertools
import logging

import eventlet
from common.dependency import PoolProvider
from common.dp.generic import GenericRpcProxy
from common.utils import log_all
from nameko.rpc import RpcProxy
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

    generic_rpc = GenericRpcProxy()
    """
    :type: common.dp.generic.GenericServiceProxyPool
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

    @log_all
    def start(self):
        logger.debug("starting query ")
        count = 0
        tot = 0
        maxi = 5000
        begin = datetime.datetime.now()
        while tot < maxi:
            with eventlet.Timeout(1, exception=False):
                for count in itertools.count():
                    if count + tot > maxi:
                        break
                    self.generic_rpc.get("producer").get()

            tot += count
            logger.debug("{} calls/s".format(count))
        end = datetime.datetime.now()
        delta = end - begin
        logger.debug("done %d calls in %d.%d sec", tot, delta.total_seconds(), delta.microseconds)

    @http('GET', '/')
    @log_all
    def trigger(self, request):
        self.pool.spawn(self.start)
        return '<html><body><h3>started 5000 queries to Consumer</h3></body></html>'
