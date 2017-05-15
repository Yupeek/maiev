# -*- coding: utf-8 -*-
"""
this contains the serializer that will accept a datetime to transmit througth rabbitmq
"""

import datetime
import json
import logging
from time import mktime

logger = logging.getLogger(__name__)


class DateCompatibleJSONEncode(json.JSONEncoder):
    def default(self, obj):

        if isinstance(obj, datetime.date):
            return {
                '__type__': '__date__',
                'epoch': int(mktime(obj.timetuple()))
            }
        elif isinstance(obj, datetime.datetime):
            return {
                '__type__': '__datetime__',
                'epoch': int(mktime(obj.timetuple()))
            }
        else:
            return json.JSONEncoder.default(self, obj)


def datecompatible_decoder(obj):
    if '__type__' in obj:
        if obj['__type__'] == '__datetime__':
            return datetime.datetime.fromtimestamp(obj['epoch'])
        elif obj['__type__'] == '__date__':
            return datetime.date.fromtimestamp(obj['epoch'])
    return obj


# Encoder function
def datecompatible_dumps(obj):
    return json.dumps(obj, cls=DateCompatibleJSONEncode)


# Decoder function
def datecompatible_loads(obj):
    return json.loads(obj, object_hook=datecompatible_decoder)


register_args = (
    datecompatible_dumps,
    datecompatible_loads,
    'application/x-myjson',
    'utf-8'
)


def register_datecompatible_serializer():
    from kombu.serialization import register
    register('json_datecompatible', *register_args)
