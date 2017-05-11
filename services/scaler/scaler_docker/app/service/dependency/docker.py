# -*- coding: utf-8 -*-

import logging
from docker import client

from nameko.extensions import DependencyProvider


logger = logging.getLogger(__name__)


class DockerClientProvider(DependencyProvider):

    def setup(self):
        docker_cfg = self.container.config.get('DOCKER', {})
        if docker_cfg:
            self.client = client.DockerClient(**docker_cfg)
        else:
            self.client = client.from_env()
        self.client.info()

    def get_dependency(self, worker_ctx):
        return self.client
