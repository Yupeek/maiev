# -*- coding: utf-8 -*-
import logging
import pydoc

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
