# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import logging
from functools import wraps, partial

import types
from eventlet import sleep
from nameko.extensions import Entrypoint


def log_all(meth_or_ignore_excpt=None, ignore_exceptions=(SystemExit, )):
    if isinstance(meth_or_ignore_excpt, types.FunctionType):

        meth = meth_or_ignore_excpt
        logger = logging.getLogger(meth.__module__ or __name__)
        @wraps(meth)
        def wrapper(*args, **kwargs):
            try:
                return meth(*args, **kwargs)
            except ignore_exceptions:
                raise
            except Exception:
                logger.exception("error on %s", meth.__name__)
                raise
    else:
        # gave exceptions
        ignore_exceptions = meth_or_ignore_excpt or ignore_exceptions
        return partial(log_all, ignore_exceptions=ignore_exceptions)
    return wrapper


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
        sleep(1)
        self.container.spawn_worker(self, self.args, self.kwargs)

once = Once.decorator