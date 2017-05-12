# -*- coding: utf-8 -*-

import json
import logging

import docker.errors
from common.dependency import PoolProvider
from docker.types.services import ServiceMode
from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.web.handlers import http

from common.utils import log_all
from service.dependency.docker import DockerClientProvider

logger = logging.getLogger(__name__)


def split_envs(envs_from_docker):
    """
    split the list of env from docker api into a dict

    >>> split_envs(['SITENAME=localhost', 'A=bibi']) == {'SITENAME': 'localhost', 'A': 'bibi'}
    True
    
    :param envs_from_docker: 
    :return: 
    """
    return dict(a.split('=') for a in envs_from_docker)


def parse_full_id(image_full):
    """
    parse the full path of an image and return the splited element:
    
    - repository
    - image name
    - tag
    - digest
    
    :param image_full: the full image (docker.io/image:tag@sha
    :return: 
    """

    if '@' in image_full:
        rest, digest = image_full.split('@')
    else:
        rest, digest = image_full, None
    if '/' in rest:
        # with repo
        splited = rest.split('/')
        repo = '/'.join(splited[:-1])
        image_n_tag = splited[-1]
    else:
        repo = ''
        image_n_tag = rest
    if ':' in image_n_tag:
        image_name, tag = image_n_tag.split(':')
    else:
        image_name, tag = image_n_tag, 'latest'

    result = {'image': image_name, 'repository': repo, 'tag': tag, 'digest': digest}
    logger.debug("parsed %s into %s", image_full, result)
    return result


def recompose_full_id(decomposed):
    """
    recompose the full image identifier from a naive deconstructed data
    
    >>> recompose_full_id({'name': 'nginx'})
    'nginx'
    >>> recompose_full_id({'name': 'nginx', 'repository': 'localdocker:5000/', 'tag': 'latest', \
            'digest': 'sha256:a45a0eda30eb0908edb977d42f2369b78d97cea58ffcde158d5e4d000e076932'})
    'localdocker:5000/nginx@sha256:a45a0eda30eb0908edb977d42f2369b78d97cea58ffcde158d5e4d000e076932'
    
    :param decomposed: the dict with decomposed data 
    :return: the full id of an image
    """
    if 'name' not in decomposed:
        raise Exception("can't recompose id without even the image name for %s" % decomposed)
    res = decomposed['name']
    if decomposed.get('repository'):
        res = "%s/%s" % (decomposed['repository'].strip('/'), res)
    if decomposed.get('version'):
        res = '%s:%s' % (res, decomposed['version'])
    if decomposed.get('digest'):
        res = "%s@%s" % (res, decomposed['digest'])
    logger.debug("recomposed %s into %s ", decomposed, res)
    return res


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
    type = 'docker'
    dispatch = EventDispatcher()
    docker = DockerClientProvider()  #
    """
    :type: docker.client.DockerClient
    """
    pool = PoolProvider()
    """
    :type: eventlet.greenpool.GreenPool
    """

    @http('POST', '/event')
    @log_all
    def event(self, request):
        """
        entry point for docker repository notification
        :param werkzeug.wrappers.Request request: the request 
        :return: 
        """
        logger.debug("data from request: %s", request.get_data(as_text=True))

        @log_all
        def propagate_events():
            try:
                data = json.loads(request.get_data(as_text=True))
                for event in data['events']:
                    target = event['target']
                    logger.debug('event from repo: %s', target)

                    if event['action'] == 'push':
                        event_payload = {
                            'from': self.name,
                            'digest': target['digest'],
                            'image_name': target['repository'],
                            'full_image_id': '%s/%s@%s' % (event['request']['host'], target['repository'], target['digest'])
                        }
                        if 'tag' in target:
                            event_payload['version'] = target['tag']
                        try:
                            event_payload['scale_config'] = self.fetch_image_config(event_payload['full_image_id'])
                        except docker.errors.DockerException:
                            logger.exception("error while fetching image config for %s" % event_payload['full_image_id'])

                        self.dispatch('image_updated', event_payload)
                        logger.debug("dispatching %s", event_payload)
            except Exception:
                logger.exception("error while receiving docker push notification")
        self.pool.spawn(propagate_events)

        return ''

    @rpc
    @log_all
    def update(self, service_name, image_id=None, scale=None):
        """
        update the given service with the given image
        :param image_id: 
        :return: 
        """
        logger.debug("upgrading %s to %s scale=%s", service_name, image_id, scale)
        service = self._get(service_name=service_name)
        attrs = {}
        if image_id is not None:
            attrs['image'] = image_id
        if scale is not None:
            if scale == -1:
                attrs['mode'] = ServiceMode('global', 1)
            else:
                attrs['mode'] = ServiceMode('replicated', scale)
        service.update_preserve(**attrs)

        self.dispatch('service_updated', {'service': self.get(service_id=service.id)})

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
        return self._build_service_stat(service)

    @rpc
    @log_all
    def list_services(self):
        """
        list all running service on this cluster.
        
        :return: 
        :rtype: list[dict[str, str|dict]] 
        """
        logger.debug("current service list : %d" % len(self.docker.services.list()))

        return [
            self._build_service_stat(s)
            for s in self.docker.services.list()
        ]

    @rpc
    @log_all
    def fetch_image_config(self, image_full_id):
        if isinstance(image_full_id, dict):
            # we got all decomposed data.
            image_full_id = image_full_id.get('image_full_id', None) or recompose_full_id(image_full_id)
        try:
            result = self.docker.containers.run(image_full_id, 'scale_info', remove=True).decode('utf-8')
        except docker.errors.NotFound:
            logger.exception("docker image %s don't contains scale_info executable", image_full_id)
            return None
        else:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                logger.exception("docker image %s has invalide scale_info output", image_full_id)
                return None

    # ####################################################
    #                 PRIVATE
    # ####################################################

    def _build_service_stat(self, service):
        """
        build the service stats with the folowing values :
        
        - name: name of the service
        - image: the name of the image
        - version: the versio of the image
        - repository
        - ports: the list of the port accessible by this service {'published', 'target'}
        - intances: the list of tasks (runnings or downs)
        - envs: the list of env configured to this service
        - mode: mode, numbers
        
        :param service: 
        :return: 
        """
        image_full_id = service.attrs['Spec']['TaskTemplate']['ContainerSpec']['Image']
        image_data = parse_full_id(image_full_id)

        if 'Replicated' in service.attrs['Spec']['Mode']:
            mode = {
                'name': 'replicated',
                'replicas': service.attrs['Spec']['Mode']['Replicated']['Replicas'],
            }
        elif 'Global' in service.attrs['Spec']['Mode']:
            mode = {
                'name': 'global',
            }
        else:
            mode = {
                'name': 'unknown'
            }
        return {
            'name': service.name,
            'full_image_id': image_full_id,
            'image': image_data['image'],
            'version': image_data['tag'],
            'repository': image_data['repository'],
            'ports': [
                {'published': d['PublishedPort'],
                 'target': d['TargetPort']
                 } for d in service.attrs['Endpoint']['Ports']
            ],
            'instances': [
                self._build_task_stats(task) for task in service.tasks()
            ],
            'envs': split_envs(service.attrs['Spec']['TaskTemplate']['ContainerSpec'].get('Env', [])),
            'mode': mode,

        }

    def _build_task_stats(self, task):
        image_data = parse_full_id(task['Spec']['ContainerSpec']['Image'])
        return {
            'is_running': task['Status']['State'] == 'running',
            'image': image_data['image'],
            'version': image_data['tag'],
            'repository': image_data['repository'],
            'updated_at': task['UpdatedAt']
        }

    def _get(self, service_id=None, service_name=None):
        """
        fetch the docker api service from the backend
        :param str service_name: the name of the service 
        :param str service_id: the Id of the service
        :return: the service or None
        :rtype: docker.models.services.Service
        """
        if service_id:
            service = self.docker.services.get(service_id)
        elif service_name:
            services = self.docker.services.list(filters=dict(name=service_name))
            if services:
                service = services[0]
            else:
                service = None
        else:
            raise ValueError("can't get a service without eiter his name or his id")
        return service
