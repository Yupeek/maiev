# -*- coding: utf-8 -*-
import logging

from nameko.extensions import DependencyProvider
from nameko.rpc import ReplyListener, ServiceProxy

logger = logging.getLogger(__name__)


class GenericServiceProxyPool(object):

    def __init__(self, worker_ctx, rpc_reply_listener):
        self.worker_ctx = worker_ctx
        self.proxy = {}
        self.rpc_reply_listener = rpc_reply_listener

    def get(self, service, **options):
        try:
            res = self.proxy[service]
        except KeyError:

            res = self.proxy[service] = ServiceProxy(
                self.worker_ctx,
                service,
                self.rpc_reply_listener,
                **options
            )
        return res


class GenericRpcProxy(DependencyProvider):
    rpc_reply_listener = ReplyListener()

    def __init__(self):
        self.pool = None

    def get_dependency(self, worker_ctx):

        self.pool = pool = GenericServiceProxyPool(worker_ctx, self.rpc_reply_listener)
        return pool
