# -*- coding: utf-8 -*-
import logging
from logging import Filter

logger = logging.getLogger(__name__)


class FilterGetRoot(Filter):

    def filter(self, record):
        return '"GET / HTTP/1.1"' not in record.msg
