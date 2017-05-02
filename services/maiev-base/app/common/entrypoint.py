# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import logging

from eventlet import sleep
from nameko.extensions import Entrypoint

logger = logging.getLogger(__name__)


class Once(Entrypoint):
    """ Entrypoint that spawns a worker exactly once, as soon as
    the service container started.
    """
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self):
        self.container.spawn_managed_thread(self._run)
        pass

    def _run(self):
        logger.debug("will spawn worker soon")
        sleep(1)
        self.container.spawn_worker(self, self.args, self.kwargs)


once = Once.decorator