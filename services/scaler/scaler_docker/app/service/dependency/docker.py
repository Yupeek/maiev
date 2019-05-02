# -*- coding: utf-8 -*-

import logging

from docker import client
from nameko.extensions import DependencyProvider

logger = logging.getLogger(__name__)


class DockerClientProvider(DependencyProvider):

    def setup(self):
        docker_cfg = self.container.config.get('DOCKER')
        if docker_cfg:
            self.client = client.Client(**docker_cfg)
        else:
            self.client = client.from_env()
        self.client.info()
        self.event_handlers = []

    def stop(self):
        for ev in self.event_handlers:
            ev.close()

    def get_dependency(self, worker_ctx):
        old_ev = self.client.events

        def events(*args, **kwargs):
            res = old_ev(*args, **kwargs)
            self.event_handlers.append(res)
            return res
        self.client.events = events
        return self.client

