# -*- coding: utf-8 -*-
import inspect
import logging
import pydoc
import traceback

from nameko.dependency_providers import Config
from nameko.rpc import rpc

from common.utils import log_all

logger = logging.getLogger(__name__)


class BaseWorkerService(object):
    """
    provide commons methods for worker
    """

    config = Config()  # type: dict

    @rpc
    @log_all
    def help(self, type_='plaintext'):
        """
        print micro_service help messages.
        :return: help text
        :rtype: str
        """
        if type_ not in ('text', 'plaintext', 'html'):
            return "bad type : %s not in %s" % (type_, ('text', 'plaintext', 'html'))
        return pydoc.render_doc(self.__class__, renderer=getattr(pydoc, type_))

    @rpc
    @log_all
    def get_config(self):
        """
        provide the current config for debugging
        :return:
        """
        return self.config

    @rpc
    @log_all
    def list_rpc(self):
        """
        return all rpc call available
        :return:
        """
        def get_kwargs(f):
            _keeps = (inspect.Parameter.KEYWORD_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)

            try:
                sig = inspect.signature(f)
                return [
                    k
                    for k, v in sig.parameters.items()
                    if v.kind in _keeps and k != 'self'
                ]
            except Exception:
                logger.exception('exception while listing rpc commands')
                return []

        return {
            f.__name__: get_kwargs(f)
            for f in self.__class__.__dict__.values()
            if 'Rpc' in (e.__class__.__name__ for e in getattr(f, "nameko_entrypoints", []))
        }

    @rpc
    @log_all
    def test_logging(self):
        """
        provide the current config for debugging
        :return:
        """
        logger = logging.getLogger("%s.testlog" % self.name)
        logger.debug('this is a fake debug message ')
        logger.info('this is a fake debug message ')
        logger.warning('this is a fake debug message ')
        logger.error('this is a fake debug message ')
        try:
            raise Exception("fake exception handled triggered by hand")
        except Exception as e:
            logger.exception('this is a fake debug message: %s' % e)
        raise Exception("fake exception unhandled triggered by hand")
