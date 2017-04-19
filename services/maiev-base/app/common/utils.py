# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import datetime
import logging
import types
from functools import wraps, partial

import eventlet
from promise.promise import Promise


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


def make_promise(result_async):
    def promise_caller(resolve, reject):
        def promise_waiter():
            resolve(result_async.result())  # will wait for rcp reply
        eventlet.spawn(promise_waiter)
    return Promise(promise_caller)


def then(result_async):
    """
    helper to decorat a `then` with the async result.
    :param result_async: 
    :return: 
    """
    return make_promise(result_async).then


def filter_dict(d, startswith='_'):
    """
    helper that filter all key of a dict to remove each one that start with `startswith`
    :param d: the dict to filter
    :param startswith: the chars to detect 
    :return: 
    """
    return {k: v for k, v in d.items() if not k.startswith(startswith)}


def from_iso_date(dt_str):
    """
    parse the given date in iso format  ie `2017-04-18T09:02:58.649791086Z` and return a datetime
    
    >>> from_iso_date('2017-04-18T09:02:58.649791086Z')
    datetime.datetime(2017, 4, 18, 9, 13, 47, 791086)
    
    :param dt_str: the date format 
    :return: 
    """
    dt, _, us= dt_str.partition(".")
    dt= datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
    us= int(us.rstrip("Z"), 10)
    return dt + datetime.timedelta(microseconds=us)


def merge_dict(into, *args):
    """
    take many args and merge them into `into`.
    rule for replacing is : 
    - preserve existing key
    - insert new key for dict
    - replace list if don't exist
    - recursively merge dicts
    
    >>> a = {}
    >>> merge_dict(a, {'b': 1}, {'b': 2, 'c': 2})
    True
    >>> a == {'b': 1, 'c': 2}
    True
    
    >>> a = {'items': {}, 'values': {'min': 1, 'max': 4}}
    >>> merge_dict(a, {'name': 'service', 'values': {'min': 2, 'ratio': 0.5}})
    True
    >>> a == {'items': {}, 'name': 'service', 'values': {'min': 1, 'max': 4, 'ratio': 0.5}}
    True

    :param into: the dict that will be updated
    :param args: all other dict to merge value into
    :return: true if `into` was updated
    """
    updated = False
    for other in args:
        for k, v in other.items():
            if k in into and isinstance(v, dict) and isinstance(into[k], dict):
                updated = merge_dict(into[k], v) or updated
            elif k not in into:
                into[k] = v
                updated = True
    return updated

