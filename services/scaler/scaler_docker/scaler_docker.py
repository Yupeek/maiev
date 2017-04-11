# -*- coding: utf-8 -*-

import logging

import json
import types
from functools import wraps, partial

from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.web.handlers import http

from components.dependency.docker import DockerClientProvider

logger = logging.getLogger(__name__)


def log_all(meth_or_ignore_excpt=None, ignore_exceptions=(SystemExit, )):
    if isinstance(meth_or_ignore_excpt, types.FunctionType):
        meth = meth_or_ignore_excpt
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


def split_envs(envs_from_docker):
    """
    split the list of env from docker api into a dict

    >>> split_envs(['SITENAME=localhost', 'A=bibi']) == {'SITENAME': 'localhost', 'A': 'bibi'}
    True
    
    :param envs_from_docker: 
    :return: 
    """
    return dict(a.split('=') for a in envs_from_docker)


class ScalerDocker(object):
    """
    the docker swarm adapter
    
    emited event
    ############
    
    - image_updated(): ScaleConfig 
     
    subscribe
    #########
    
    None
    
    rcp
    ###
    
    fetch_image_config(image_name: str): ScaleConfig
    scale(service_nane: str, n: int)
    get(service_name: str): list[Instance]
    
    """
    name = 'scaler_docker'
    dispatch = EventDispatcher()
    docker = DockerClientProvider()  #
    """
    :type: docker.client.DockerClient
    """

    @http('POST', '/event')
    def event(self, request):
        """
        entry point for docker repository notification
        :param werkzeug.wrappers.Request request: the request 
        :return: 
        """
        try:
            data = json.loads(request.get_data(as_text=True))
            for event in data['events']:
                target = event['target']
                if event['action'] == 'push':
                    event_payload = {
                        "from": self.name,
                        "digest": target['digest'],
                        "image_name": target['repository'],

                        "image_id": "%s/%s@%s" % (event['request']['host'], target['repository'], target['digest'])
                    }
                    if 'tag' in target:
                        event_payload['version'] = target['tag']
                    self.dispatch('image_updated', event_payload)
                    logger.debug("dispatching %s", event_payload)
        except Exception:
            logger.exception("error while receiving docker push notification")

        return 200, ''

    @rpc
    def upgrade(self, service_name, image_id):
        """
        update the given service 
        :param image_name: 
        :param image_id: 
        :return: 
        """
        service = self._get(service_name=service_name)

        service.update(image=image_id)

    @rpc
    @log_all(ValueError)
    def get(self, service_id=None, service_name=None):
        """
        retreive a service data by either his name or better: his id
        :param str service_name: the name of the service 
        :param str service_id: the Id of the service
        :return: the service 
        :rtype: Service
        """
        service = self._get(service_id=service_id, service_name=service_name)
        return service

    @rpc
    @log_all
    def list_services(self):
        """
        list all running service on this cluster.
        
        :return: the list of running service, in the form of tuple, containing :
                  - str: service name
                  - str: image identifier
                  - dict[str, str] list of envs
                
        
        :rtype: list[(str, str, dict[str, str])] 
        """
        return [
            (
                s.name,
                s.attrs['Spec']['TaskTemplate']['ContainerSpec']['Image'],
                split_envs(s.attrs['Spec']['TaskTemplate']['ContainerSpec']['Env'])
            ) for s in self.docker.services.list()
        ]

    def _get(self, service_id=None, service_name=None):
        """
        fetch the docker api service from the backend
        :param str service_name: the name of the service 
        :param str service_id: the Id of the service
        :return: the service 
        :rtype: docker.models.services.Service
        """
        if service_id:
            service = self.docker.services.get(service_id)
        elif service_name:
            service = self.docker.services.list(service_name=service_name)[0]
        else:
            raise ValueError("can't get a service without eiter his name or his id")
        return service