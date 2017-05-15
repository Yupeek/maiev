# -*- coding: utf-8 -*-

import logging

import eventlet.greenpool
from nameko.constants import MAX_WORKERS_CONFIG_KEY
from nameko.extensions import DependencyProvider

logger = logging.getLogger(__name__)


class PoolProvider(DependencyProvider):

    def __init__(self):
        self.pool = None
        self.poolsize = 10

    def setup(self):
        self.poolsize = self.container.config.get(MAX_WORKERS_CONFIG_KEY, 10)

    def start(self):
        self.pool = eventlet.greenpool.GreenPool(self.poolsize)

    def stop(self):
        self.pool.waitall()

    def kill(self):
        self.pool = None

    def get_dependency(self, worker_ctx):
        return self.pool
