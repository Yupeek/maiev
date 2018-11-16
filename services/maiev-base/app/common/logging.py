# -*- coding: utf-8 -*-
import logging
from logging import Filter

from logstash_async.formatter import LOGSTASH_MESSAGE_FIELD_LIST, LogstashFormatter

try:
    import ujson as json
except ImportError:
    import json


logger = logging.getLogger(__name__)


class FilterGetRoot(Filter):

    def filter(self, record):
        return '"GET / HTTP/1.1"' not in record.msg


class JsonFormatter(LogstashFormatter):
    def _serialize(self, message):

        return json.dumps(message)

    def _move_extra_record_fields_to_prefix(self, message):
        """
        Anythng added by the "extra" keyword in the logging call will be moved into the
        configured "extra" prefix. This way the event in Logstash will be clean and any extras
        will be paired together in the configured extra prefix.
        If not extra prefix is configured, the message will be kept as is.
        """
        if not self._extra_prefix:
            return  # early out if no prefix is configured

        field_skip_list = LOGSTASH_MESSAGE_FIELD_LIST + [self._extra_prefix]
        dest = message[self._extra_prefix]['extra'] = {}
        for key in list(message):
            if key not in field_skip_list:
                dest[key] = message.pop(key)
