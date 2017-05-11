# -*- coding: utf-8 -*-

import logging

import atexit
import os
import subprocess
import tempfile
import shutil
import time
from nameko.extensions import DependencyProvider

from pymongo import MongoClient
import pymongo.errors

logger = logging.getLogger(__name__)

MONGO_URIS_KEY = 'MONGO_URIS'


class Mongo(DependencyProvider):
    def __init__(self, db_name=None):
        self.db_name = db_name
        self.db = None
        self.mongo_uri = None

    def setup(self):
        if self.db_name is None:
            self.db_name = self.container.service_cls.name
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


class MongoTemporaryInstance(object):
    """Singleton to manage a temporary MongoDB instance

    Use this for testing purpose only. The instance is automatically destroyed
    at the end of the program.

    """
    _instance = None
    MONGODB_TEST_PORT = 8749

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            atexit.register(cls._instance.shutdown)
        return cls._instance

    def __init__(self):
        self._tmpdir = tempfile.mkdtemp()
        self._process = subprocess.Popen(['mongod', '--bind_ip', 'localhost',
                                          '--port', str(self.MONGODB_TEST_PORT),
                                          '--dbpath', self._tmpdir,
                                          '--nojournal', '--nohttpinterface',
                                          '--noauth', '--smallfiles',
                                          '--syncdelay', '0',
                                          '--maxConns', '10',
                                          '--nssize', '1', ],
                                         stdout=open(os.devnull, 'wb'),
                                         stderr=subprocess.STDOUT)

        # XXX: wait for the instance to be ready
        #      Mongo is ready in a glance, we just wait to be able to open a
        #      Connection.
        for i in range(150):
            time.sleep(0.002)
            try:
                self._conn = MongoClient('localhost', self.MONGODB_TEST_PORT)
            except pymongo.errors.ConnectionFailure:
                continue
            else:
                break
        else:
            self.shutdown()
            assert False, 'Cannot connect to the mongodb test instance'

    @property
    def conn(self):
        return self._conn

    def shutdown(self):
        if self._process:
            self._process.terminate()
            self._process.wait()
            self._process = None
            shutil.rmtree(self._tmpdir, ignore_errors=True)