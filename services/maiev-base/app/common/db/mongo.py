# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import, print_function

import logging
from nameko.extensions import DependencyProvider

from pymongo import MongoClient

logger = logging.getLogger(__name__)

MONGO_URIS_KEY = 'MONGO_URIS'


class Mongo(DependencyProvider):
    def __init__(self, db_name='main'):
        self.db_name = db_name
        self.db = None
        self.mongo_uri = None

    def setup(self):
        logger.debug(self.container.service_cls.name)
        self.mongo_uri = self.container.config.get(MONGO_URIS_KEY) or self.get_default_name()

    def get_default_name(self):
        return '%s_mongodb' % self.container.service_cls.name

    def start(self):
        self.db = MongoClient(self.mongo_uri)[self.db_name]

    def stop(self):
        self.db = None

    def kill(self):
        self.db = None

    def get_dependency(self, worker_ctx):
        return self.db
