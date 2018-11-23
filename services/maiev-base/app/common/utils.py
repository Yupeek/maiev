# -*- coding: utf-8 -*-

import datetime
import logging
import re
import types
from functools import partial, wraps

import eventlet
from promise.promise import Promise
from semantic_version import Version


def log_all(meth_or_ignore_excpt=None, ignore_exceptions=(SystemExit,)):
    if isinstance(meth_or_ignore_excpt, types.FunctionType):

        meth = meth_or_ignore_excpt
        logger = logging.getLogger(meth.__module__ or __name__)

        @wraps(meth)
        def wrapper(*args, **kwargs):
            try:
                return meth(*args, **kwargs)
            except ignore_exceptions:
                raise
            except Exception as e:
                try:
                    msg = 'error with call %s(args=%r, kwargs=%r) : %s' % (meth.__name__, args, kwargs, e)
                except Exception:
                    msg = 'error with call %s(args unavailable) : %s' % (meth.__name__, e,)

                logger.exception(msg, extra={'call': {'args': args, 'kwargs': kwargs}})
                raise
    else:
        # gave exceptions
        ignore_exceptions = meth_or_ignore_excpt or ignore_exceptions
        return partial(log_all, ignore_exceptions=ignore_exceptions)
    return wrapper


def make_promise(result_async):
    def promise_caller(resolve, reject):
        def promise_waiter():
            resolve(result_async.result())  # will wait for rpc reply

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
    dt, _, us = dt_str.partition(".")
    dt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
    us = int(us.rstrip("Z"), 10)
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


class ImageVersion(object):
    """
    an object which represent an image version/tag/repository.
    it parse data from docker and can be used for equiality and inequality compartion.

    it use the folowing info from hints to know the image info :

    image-identifier : repo, image-name, [tag], metadata['image']
    version identifier: tag, metadata['version']

    this support for sub-image consideration in the tag (repo/globalservice:subservice-version)

    """
    _VERSION_REGEXP = r'(\d+)(?:\.(\d+)(?:\.(\d+))?)?(?:([0-9a-zA-Z.]*))?(?:\+([0-9a-zA-Z.]*))?'
    tag_regex = re.compile('^((?P<version>%s|latest)|-|(?P<species>[a-zA-Z_]+))+$' % _VERSION_REGEXP)
    """
    the rexexp to parse the tage: see https://regex101.com/r/o2hr5V/3
    """

    def __init__(self, data):
        """
        create an image Version using the given hints.
        hints should be a docker image datas (repo, image-name, tags)
        :param dict hints: the firts from which we parse the current version. must contains:

            - repository: the repository_name
            - image: the image name
            - tag: the tag of the image
            - digest: the digest of the image
            - [facultative] metada: a set of metadata (including 'image' and 'version')

        """
        self.data = data

    @classmethod
    def from_scaler(cls, hints):
        return cls(cls.parse(hints))

    @classmethod
    def parse(cls, hints):
        """
        parse the hints into a tuple of parsed_raw data
        :param dict hints: the hint as taken from the hints
        :rtype: dict
        :return: the dict with the finaly parsed_raw data

        - repository: the repository
        - image: the name of the image in the repository
        - species: the name of the species of this image
        - tag: the full tag, unpersed for version and species
        - version: the version, parsed_raw from tag or metadata if possible
        - digest: the digest of the image
        """
        image = hints['image']
        tag = hints.get('tag')
        result = {
            'repository': hints.get('repository'),
            'image': image,
            'tag': tag,
            'species': None,
            'version': None,
            'digest': hints.get('digest')
        }
        if tag is not None:
            parsed_raw = cls.tag_regex.match(tag)
            if parsed_raw:
                result.update(parsed_raw.groupdict())
        return result

    def is_same_image(self, other):
        """
        check if the two Version match the same image
        :param other:
        :return:
        """
        d, o = self.data, other.data
        return (
            d['repository'] == o['repository']
            and d['image'] == o['image']
            and d['species'] == o['species']
        )

    def __eq__(self, other):
        if not self.is_same_image(other):
            return False
        if self.data['version'] == 'latest':
            return other.data['version'] == 'latest' and self.data['digest'] == other.data['digest']
        else:
            return self.version == other.version

    def __hash__(self):
        d = self.data
        return hash((d[attr] for attr in ['repository', 'image', 'species', 'version']))

    def __lt__(self, other):
        sv = self.data['version']
        ov = other.data['version']
        return (
            self.is_same_image(other)
            and sv is not None
            and ov is not None
            and sv != 'latest'
            and (
                ov == 'latest'
                or self.version < other.version
            )
        )

    def __gt__(self, other):
        sv = self.data['version']
        ov = other.data['version']
        return (
            self.is_same_image(other)
            and sv is not None
            and ov is not None
            and (
                sv == 'latest'
                or self.version > other.version
            )
        )

    @property
    def version(self):
        if self.data['version'] in (None, 'latest'):
            return self.data['version']
        else:
            return Version.coerce(self.data['version'])

    @property
    def image_id(self):
        """
        return a string which represent the image identifier.
        it is used for database query
        :return:
        """
        return "{repository}/{image}:{species}".format(**self.data)

    @property
    def unique_image_id(self):
        """
        return the unique id of this image, including tags and digest
        :return:
        """
        res = "{repository}/{image}:{tag}".format(**self.data)
        if self.data['digest']:
            res += "@%s" % self.data['digest']
        return res

    def __repr__(self):
        return "<ImageVersion {image_id} version={version}>".format(image_id=self.image_id, **self.data)

    def __str__(self):
        return "ImageVersion {image_id} version={version}".format(image_id=self.image_id, **self.data)

    def serialize(self):
        return self.data

    @classmethod
    def deserialize(cls, data):
        """

        :param data: remake a ImageVersion from a previous «serialize» output
        :return: a ImageVersion
        :rtype: ImageVersion
        """
        return cls(data)
