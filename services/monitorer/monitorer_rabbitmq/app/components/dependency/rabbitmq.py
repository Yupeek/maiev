# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import logging
import urllib.parse
from json.decoder import JSONDecodeError

import requests
from nameko.extensions import DependencyProvider

logger = logging.getLogger(__name__)
RABBITMQ_URLS_KEY = 'MONITORED_SERVER_URL'


class RabbitMqApi(object):
    def __init__(self, base_url):
        self.base_url = base_url.lstrip('/') + '/'
        self.session = requests.session()

    def _get(self, *url_parts, params=None):
        final_url = urllib.parse.urljoin(self.base_url, "/".join([urllib.parse.quote(p, '') for p in url_parts]))
        if params:
            final_url += "?%s" % urllib.parse.urlencode(params)

        response = self.session.get(final_url)

        if response.status_code == 404:
            logger.exception("the requested ressource does not exists for %s", url_parts)
            return None
        try:
            return response.json()
        except JSONDecodeError:
            logger.exception("error while decoding rabbitmq backend response: %s", response.text)
            raise

    def get_queue_stats(self, qname, **extra):
        return self._get('queues', '/', qname, params=extra)


class RabbitMq(DependencyProvider):
    def __init__(self, vhost_name='vhost'):
        self.vhost_name = vhost_name
        self.rabbitmq_url = None
        self.api = None

    def get_default_url(self):
        broker = self.container.config['AMQP_URI']
        parsed = urllib.parse.urlparse(broker)
        netloc = parsed.netloc
        if parsed.port is None:
            netloc += ":15672"

        url = urllib.parse.urlunparse(('http', netloc, 'api',) + ('',) * 3)
        return url

    def setup(self):
        self.rabbitmq_url = self.container.config.get(RABBITMQ_URLS_KEY) or self.get_default_url()

    def get_default_name(self):
        return '%s_mongodb' % self.container.service_cls.name

    def start(self):
        self.api = RabbitMqApi(self.rabbitmq_url)

    def stop(self):
        self.api = None

    def kill(self):
        self.api = None

    def get_dependency(self, worker_ctx):
        return self.api

