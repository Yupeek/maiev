# -*- coding: utf-8 -*-
import json
import logging
import os
import re
from json import JSONDecodeError

import requests

logger = logging.getLogger(__name__)


def cached(func):
    def wrapper(self, *args):

        try:
            res = self.auth_tokens_cache[args]
        except AttributeError:
            self.auth_tokens_cache = {}
            res = self.auth_tokens_cache[args] = func(self, *args)
        except KeyError:
            res = self.auth_tokens_cache[args] = func(self, *args)
        return res
    return wrapper


class Registry:
    image_parse_regex = re.compile(r'''
        ^
        (?:
            (?P<host>[a-zA-Z](?=[^/]*[.:]).*)
            /
        )?
        (?P<image>(?:\w+|/)+)
        (?::
            (?P<TAG>[-.a-zA-Z_0-9]*)
        )?
    ''', re.VERBOSE)

    @cached
    def get_basic_auth(self, registry):
        """
        return the registry token from .docker/config.json (docker login cred)
        :param registry:
        :return:
        """
        config_path = os.path.join(os.environ.get('HOME', '/root/'), '.docker', 'config.json')
        config = json.load(open(config_path, encoding='utf-8'))

        if registry == 'index.docker.io':
            with_scheme = 'https://index.docker.io/v1/'
            without_scheme = None
        elif registry.startswith('http'):
            with_scheme = registry
            without_scheme = registry.replace('https://', '').replace('http://', '')
        else:
            with_scheme = 'https://%s' % registry
            without_scheme = registry

        try:
            return config['auths'][with_scheme]['auth']
        except KeyError:
            try:
                return config['auths'][without_scheme]['auth']
            except KeyError:
                return None

    @cached
    def get_auth_header(self, host, image):
        """
        return auth header.
        :param host: the host of the registry
        :param image:
        :return:
        """
        auth = self.get_basic_auth(host)
        if auth is None:
            return None
        if host != 'index.docker.io':
            # a image with a host: it's a private registry
            return "Basic %s" % auth
        else:
            # this is the official registry. we must pre-auth against auth.docker.io
            res = requests.get("https://auth.docker.io/token?service=registry.docker.io&scope=repository:{image}:pull".
                               format(image=image),
                               headers={"Accept": "application/json",
                                        "Authorization": "Basic %s" % auth})
            try:
                return "Bearer %s" % res.json()['token']
            except (JSONDecodeError, KeyError):
                logger.exception("error in auth request %s. can't fetch token for registry %s and image %s" % (
                    res.text, host, image))
                return None

    def list_tags(self, full_image):
        match = self.image_parse_regex.match(full_image)
        if match is None:
            logger.error("can't parse image %s into registry+image+tags", full_image)
            return
        image = match.groupdict()

        if not image.get('host'):
            image['host'] = "index.docker.io"

            if '/' not in image['image']:
                image['image'] = 'library/%s' % image['image']

        auth_header = self.get_auth_header(image['host'], image['image'])
        headers = {"Accept": "application/json"}
        if auth_header:
            headers['Authorization'] = auth_header

        res = requests.get("http://{host}/v2/{image}/tags/list".format(**image), headers=headers).json()
        if 'tags' in res:
            return res['tags']
        else:
            logger.debug("no tags found for %s: %s", full_image, res)
            return []
