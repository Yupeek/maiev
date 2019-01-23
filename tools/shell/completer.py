# -*- coding: utf-8 -*-
import logging
import types
import urllib.parse
from functools import singledispatch

import IPython
import requests
from IPython.core.error import TryNext
from IPython.utils.generics import complete_object
from nameko.rpc import ServiceProxy, MethodProxy
from nameko.standalone.rpc import ClusterProxy

logger = logging.getLogger(__name__)

latest_query = {}

services_results = {}

services_list = []

print("adding service completion for n.rpc.* ")


@complete_object.register(ServiceProxy)
def complete_rpc(service, prev_compl):

    try:
        service_name = service.service_name
        if service_name in services_results:
            res = services_results[service_name]
        else:
            res = services_results[service_name] = service.list_rpc()
        return list(res)
    except Exception as e:
        latest_query.clear()
        latest_query['exception'] = e
        latest_query['service'] = service
        latest_query['prev_compl'] = prev_compl
        raise TryNext


completer = IPython.get_ipython().Completer
completer._default_arguments = singledispatch(completer._default_arguments)


def complete_args(self, method):
    try:
        service_name = method.service_name
        if service_name in services_results:
            res = services_results[service_name]
        else:
            res = services_results[service_name] = getattr(self.namespace['n'].rpc, service_name).list_rpc()
        return res[method.method_name]
    except Exception as e:
        latest_query.clear()
        latest_query['exception'] = e
        latest_query['self'] = self
        latest_query['method'] = method
        raise TryNext


completer._default_arguments.register(MethodProxy)(types.MethodType(complete_args, completer))


@complete_object.register(ClusterProxy)
def complete_services(cluster, prev_compl):
    if services_list:
        return services_list

    try:
        broker = IPython.get_ipython().Completer.namespace['n'].config['AMQP_URI']
        parsed = urllib.parse.urlparse(broker)
        netloc = parsed.netloc
        if parsed.port is None:
            netloc += ":15672"

        url = urllib.parse.urlunparse(('http', netloc, 'api',) + ('',) * 3)

        queues = [q['name'] for q in requests.get(url + '/queues').json()]
        services_list.extend([
            n.replace('rpc-', '') for n in queues
            if n.startswith('rpc-')
        ])
        return services_list
    except Exception as e:
        latest_query.clear()
        latest_query['exception'] = e
        latest_query['cluster'] = cluster
        latest_query['prev_compl'] = prev_compl
        raise TryNext

