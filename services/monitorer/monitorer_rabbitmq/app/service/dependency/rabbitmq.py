# -*- coding: utf-8 -*-

import logging
import urllib.parse
from json.decoder import JSONDecodeError

import requests
from eventlet import sleep
from nameko.extensions import DependencyProvider
from requests.exceptions import ConnectionError

logger = logging.getLogger(__name__)
RABBITMQ_URLS_KEY = 'MONITORED_SERVER_URL'
RABBITMQ_VHOST_KEY = 'MONITORED_SERVER_VHOST'


class RabbitMqApi(object):
    def __init__(self, base_url, vhost='/'):
        self.base_url = base_url.lstrip('/') + '/'
        self.session = requests.session()
        self.vhost = vhost

    def _get(self, *url_parts, params=None):
        final_url = urllib.parse.urljoin(self.base_url, "/".join([urllib.parse.quote(p, '') for p in url_parts]))
        if params:
            final_url += "?%s" % urllib.parse.urlencode(params)
        response = None
        for _ in range(3):  # retry 3 times
            try:
                response = self.session.get(final_url)
            except ConnectionError:
                self.session = requests.session()
                sleep(1)  # throthle queries
            except Exception:
                logger.exception("error while connecting to %s", final_url)
                return None
            else:
                break

        if response is None or response.status_code == 404:
            return None
        try:
            return response.json()
        except JSONDecodeError:
            logger.exception("error while decoding rabbitmq backend response: GET %s =>  [%d]%r",
                             final_url,
                             response.status_code,
                             response.text)
            raise

    def get_queue_stats(self, qname, **extra):
        return self._get('queues', self.vhost, qname, params=extra)


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

    def get_default_vhost(self):
        broker = self.container.config['AMQP_URI']
        parsed = urllib.parse.urlparse(broker)
        return parsed.path.lstrip('/') if parsed.path != '/' else parsed.path

    def setup(self):
        self.rabbitmq_url = self.container.config.get(RABBITMQ_URLS_KEY) or self.get_default_url()
        self.rabbitmq_vhost = self.container.config.get(RABBITMQ_VHOST_KEY) or self.get_default_vhost()

    def start(self):
        self.api = RabbitMqApi(self.rabbitmq_url, self.rabbitmq_vhost)

    def stop(self):
        self.api = None

    def kill(self):
        self.api = None

    def get_dependency(self, worker_ctx):
        return self.api
