# -*- coding: utf-8 -*-
import datetime
import json
import logging
import re
import time

import docker.errors
import yaml
from docker.types import SecretReference, RestartPolicy
from docker.types.services import ServiceMode, RestartConditionTypesEnum
from nameko.events import EventDispatcher
from nameko.rpc import rpc
from nameko.web.handlers import http
import re

from common.base import BaseWorkerService
from common.dependency import PoolProvider
from common.entrypoint import once
from common.utils import log_all
from service.dependency.docker import DockerClientProvider
from service.scaler_docker.registry import Registry

logger = logging.getLogger(__name__)


def split_envs(envs_from_docker):
    """
    split the list of env from docker api into a dict

    >>> split_envs(['SITENAME=localhost', 'A=bibi']) == {'SITENAME': 'localhost', 'A': 'bibi'}
    True
    >>> split_envs(['LABEL=logspout=on', 'A=bibi']) == {'LABEL': 'logspout=on', 'A': 'bibi'}
    True
    >>> split_envs(['OOPS']) == {'OOPS': ''}
    True

    :param envs_from_docker:
    :return:
    """
    res = {}
    for env_str in envs_from_docker:
        splited = env_str.split('=')
        res[splited[0]] = '='.join(splited[1:])
    return res


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
    if decomposed.get('tag'):
        res = '%s:%s' % (res, decomposed['tag'])
    if decomposed.get('digest'):
        res = "%s@%s" % (res, decomposed['digest'])
    return res


def inc_name(name):
    """
    increment the name of the given file. detectect existing number in name before extension
    :param name:
    :return:
    """
    match = re.match(r"^(?P<n>.+?)(?P<num>\d+)?(?P<ext>\.(.*))?$", name)
    if not match:
        return name + '1'
    groupdict = match.groupdict()

    n = int(groupdict.get('num') or '0')
    return "".join((
        groupdict.get('n') or '',
        "%s" % (n + 1),
        groupdict.get('ext') or ''
    ))


def escape_env_var(obj):
    """create a copy of dict_ where all $ is doubled values of dict recursively"""
    if isinstance(obj, str):
        return obj.replace('$', '$$')
    elif isinstance(obj, list):
        return [escape_env_var(i) for i in obj]
    elif isinstance(obj, dict):
        return {
            k: escape_env_var(v)
            for k, v in obj.items()
        }
    else:
        return obj


class ScalerDocker(BaseWorkerService):
    """
    the docker swarm adapter

    emited event
    ############

    - image_updated(): ScaleConfig

    subscribe
    #########

    None

    rpc
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

    # ####################################################
    #   HTTP endpoints
    # ####################################################

    @http('GET', '/')
    @rpc
    def ping(self, request):
        return 'OK'

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
                if 'events' in data:
                    self._parse_event_from_registry(data)
                else:
                    self._parse_event_from_hub(data)
            except Exception:
                logger.exception("error while receiving docker push notification")

        self.pool.spawn(propagate_events)

        return ''

    # ####################################################
    #   Once endpoints
    # ####################################################

    @once
    @log_all
    def start_listen_events(self):
        def listen_to_events():
            logger.debug("start listening for docker events")
            for event in self.docker.events(since=datetime.datetime.now(), decode=True):
                if event['Action'] == 'update' and event['Type'] == 'service':
                    logger.debug("event %s ", event)
                    logger.debug("dispatching new update event: %s" % event['Actor']['Attributes'])
                    self.dispatch('service_updated', {
                        'service': self.get(service_id=event['Actor']['ID']),
                        'attributes': event['Actor']['Attributes'],
                    })
        self.pool.spawn(listen_to_events)
    # ####################################################
    #  RPC endpoints
    # ####################################################

    @rpc
    @log_all
    def update(self, service_name, image_id=None, scale=None):
        """
        update the given service with the given image
        :param image_id:
        :return:
        """
        logger.info("upgrading %s to %s scale=%s", service_name, image_id, scale)
        service = self._get(service_name=service_name)
        attrs = {}
        if image_id is not None:
            attrs['image'] = image_id
        if scale is not None:
            if scale == -1:
                attrs['mode'] = ServiceMode('global', 1)
            else:
                attrs['mode'] = ServiceMode('replicated', scale)
        service.update(fetch_current_spec=True, **attrs)

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
    def dump(self, stack=''):
        """
        dump the given stack based on current docker data.
        this methed inspect docker to reproduce the same setup with docker stack deploy.

        this create the folowing dict :
        "filename" => "content",

        it will generate a valid docker-compose file along with required files like config or secret.
        currently don't support  (i'm lazy):
        - endpoint_mode
        - dns
        - dns_search
        - entrypoint
        - deploy.placement.preferences
        - expose
        - extra_host
        - external_link
        - healthcheck
        - init
        - isolation
        - logging



        :return:
        """
        yaml_data = {
            "version": "3.7",
            "services": {},
            "networks": {},
            "configs": {},
            "secrets": {},

        }
        files = {
        }
        namereplace = re.compile(r'^%s[_-]' % stack)

        for service in self.docker.services.list():
            try:
                spec = service.attrs['Spec']
                if spec.get('Labels', {}).get('com.docker.stack.namespace', '') != stack:
                    continue
                configs = self._dump_configs(files, namereplace, spec, yaml_data)
                secrets = self._dump_services(files, namereplace, spec, yaml_data)

                networks = self._dump_networks(namereplace, spec, yaml_data)

                if "Replicated" in spec['Mode']:
                    mode = {
                        "mode": "replicated",
                        "replicas": spec['Mode']['Replicated']['Replicas']
                    }
                else:
                    mode = {"mode": "global"}
                s_yaml = {
                    "image": spec['TaskTemplate']['ContainerSpec']['Image'],
                    "environment": spec['TaskTemplate']['ContainerSpec'].get('Env', []),
                    "configs": configs,
                    "secrets": secrets,
                    "networks": networks,
                    "volumes": [
                        {
                            "type": p['Type'],
                            "source": p['Source'],
                            "target": p['Target'],
                        } for p in spec['TaskTemplate']['ContainerSpec'].get('Mounts', [])
                    ],
                    "ports": [
                        {
                            'target': p['TargetPort'],
                            'published': p['PublishedPort'],
                            'protocol': p['Protocol'],
                            'mode': p['PublishMode'],
                        } for p in spec['EndpointSpec'].get('Ports', [])
                    ],
                    "deploy": {
                        "placement": {
                            "constraints": spec['TaskTemplate']['Placement'].get('Constraints', []),
                        },
                        "resources": {
                            "limits": spec['TaskTemplate']['Resources'].get('Limits', []),
                            "reservations": spec['TaskTemplate']['Resources'].get('Reservations', []),
                        },
                        "restart_policy": {
                            "condition": spec['TaskTemplate']['RestartPolicy']['Condition'],
                            "delay": "%ss" % (
                                spec['TaskTemplate']['RestartPolicy'].get('Delay', 5000000000) / 1000000000
                            ),  # from ns to s
                            "max_attempts": spec['TaskTemplate']['RestartPolicy']['MaxAttempts'],
                        } if spec['TaskTemplate'].get('RestartPolicy') else {},
                        "rollback_config": {
                            "parallelism": spec['RollbackConfig']["Parallelism"],
                            "failure_action": spec['RollbackConfig']["FailureAction"],
                            "monitor": spec['RollbackConfig']["Monitor"],
                            "max_failure_ratio": spec['RollbackConfig']["MaxFailureRatio"],
                            "order": spec['RollbackConfig']["Order"],
                        } if spec['TaskTemplate'].get('RollbackConfig') else {},
                        "update_config": {
                            "parallelism": spec['UpdateConfig']["Parallelism"],
                            "failure_action": spec['UpdateConfig']["FailureAction"],
                            "monitor": spec['UpdateConfig']["Monitor"],
                            "max_failure_ratio": spec['UpdateConfig']["MaxFailureRatio"],
                            "order": spec['UpdateConfig']["Order"],
                        } if spec['TaskTemplate'].get('UpdateConfig') else {},
                        **mode
                    }
                }
                args = spec['TaskTemplate']['ContainerSpec'].get('Args')
                if args:
                    s_yaml['command'] = args

                service_name = namereplace.sub('', spec['Name'])
                # double all $ in values to prevent env variable substitution of docker stack depoly
                yaml_data['services'][service_name] = escape_env_var(s_yaml)
            except Exception:
                logger.exception("error with service payload %s" % service.attrs)
                raise

        files["docker-compose.yml"] = yaml.dump(yaml_data)
        return files

    def _dump_networks(self, namereplace, spec, yaml_data):
        networks = {}
        for network_hash in spec['TaskTemplate'].get('Networks', []):
            net_obj = self.docker.networks.get(network_hash['Target'])
            network_name = namereplace.sub('', net_obj.attrs['Name'])
            yaml_data['networks'][network_name] = {
                "driver": net_obj.attrs['Driver'],
            }
            networks[network_name] = {}
        return networks

    def _dump_configs(self, files, namereplace, spec, yaml_data):
        configs = []
        for config in spec['TaskTemplate']['ContainerSpec'].get('Configs', []):
            config_name = filename = config['ConfigName']
            config_orig_name = namereplace.sub('', config['ConfigName'])
            while filename in files:
                filename = inc_name(filename)
            configs.append({
                "source": filename,
                "target": config['File']['Name'],
                "uid": config['File']['UID'],
                "gid": config['File']['GID'],
                "mode": config['File']['Mode'],
            })

            files[filename] = self.docker.configs.get(config_name).attrs['Spec']['Data']
            yaml_data['configs'][config_orig_name] = {'file': filename}
        return configs

    def _dump_services(self, files, namereplace, spec, yaml_data):
        secrets = []
        for secret in spec['TaskTemplate']['ContainerSpec'].get('Secrets', []):
            secret_name = filename = secret['SecretName']
            secret_orig_name = namereplace.sub('', secret['SecretName'])
            while filename in files:
                filename = inc_name(filename)
            secrets.append({
                "source": filename,
                "target": secret['File']['Name'],
                "uid": secret['File']['UID'],
                "gid": secret['File']['GID'],
                "mode": secret['File']['Mode'],
            })

            yaml_data['secrets'][secret_orig_name] = {
                'file': filename,
                'name': secret_orig_name
            }
            try:
                remanent = self.docker.services.list(filters=dict(name='maiev_get_secret'))
                if remanent:
                    remanent[0].remove()
            except docker.errors.APIError:
                pass
            s = self.docker.services.create(
                'bash', command=['cat', '/tmp/secret'],
                name='maiev_get_secret',
                restart_policy=RestartPolicy(RestartConditionTypesEnum.ON_FAILURE, 5, 1),
                secrets=[SecretReference(secret['SecretID'], secret_name, '/tmp/secret')]
            )
            time.sleep(0.1)
            cnt = 0
            while len(s.tasks({'desired-state': 'running'})) > 0:
                time.sleep(0.5)
                cnt += 1
                if cnt > 60:
                    raise Exception(
                        "unable to retreive secret %s. task did not start: %s" % (
                            secret_name,
                            s.tasks({'desired-state': 'running'})
                        )
                    )

            files[filename] = b"".join(s.logs(stdout=True, follow=False)).decode('utf-8')
            s.remove()
        return secrets

    @rpc
    @log_all
    def fetch_image_config(self, image_full_id):
        if isinstance(image_full_id, dict):
            # we got all decomposed data.
            image_full_id = image_full_id.get('image_full_id', None) or recompose_full_id(image_full_id)
        try:
            cmd = 'scale_info'
            result = self.docker_run(cmd, image_full_id)
        except (docker.errors.NotFound, docker.errors.ContainerError) as e:
            if "executable file not found in " not in str(e):
                logger.debug("extra error for scaler_info", exc_info=True)
            return None
        else:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                logger.exception("docker image %s has invalide scale_info output: %r", image_full_id, result)
                return None

    def docker_run(self, cmd, image_full_id, **kwargs):
        """
        execute cmd into image and return the stdout
        :param cmd:
        :param image_full_id:
        :return:
        """
        result = None
        try:
            container = self.docker.containers.run(image_full_id, cmd, remove=False, detach=True, **kwargs)
            # tricks to make sure the container has flushed stdout and we got all data
            container.logs(follow=True).decode('utf-8')
            container.stop()
            result = container.logs(follow=True).decode('utf-8')
        finally:
            try:
                container.remove()
            except Exception:
                pass
        return result

    @rpc
    @log_all
    def list_tags(self, image_full_id):
        if isinstance(image_full_id, dict):
            # we got all decomposed data.
            image_full_id = image_full_id.get('image_full_id', None) or recompose_full_id(image_full_id)
        r = Registry()
        logger.debug("interogating registry for tags in %s", image_full_id)
        return r.list_tags(image_full_id)

    # ####################################################
    #                 PRIVATE
    # ####################################################

    def _parse_event_from_registry(self, data):
        """
        parse the event from a docker registry instance and dispatch an «image_updated» for this image
        :param data:
        :return:
        """
        events = data.get('events')
        for event in events:
            target = event['target']
            logger.debug('event from repo: %s', target)

            if event['action'] == 'push':
                event_payload = {
                    'from': self.name,
                    'digest': target['digest'],
                    'image': target['repository'],
                    'repository': event['request']['host'],
                    'full_image_id': '%s/%s@%s' % (event['request']['host'],
                                                   target['repository'],
                                                   target['digest'])
                }
                if 'tag' in target:
                    event_payload['tag'] = target['tag']
                try:
                    event_payload['scale_config'] = self.fetch_image_config(event_payload['full_image_id'])
                except docker.errors.DockerException:
                    logger.exception("error while fetching image config for %s" %
                                     event_payload['full_image_id'])

                self.dispatch('image_updated', event_payload)
                logger.debug("dispatching %s", event_payload)

    def _parse_event_from_hub(self, data):
        """
        parse the event from docker hub. and dispatch an «image_updated» for this image
        :param data:
        :return:
        """
        push_data = data['push_data']
        event_payload = {
            'from': self.name,
            'digest': None,
            'image': data['repository']['name'],
            'repository': data['repository']['namespace'],
            'full_image_id': '%s/%s:%s' % (data['repository']['namespace'], data['repository']['name'],
                                           push_data['tag']), 'tag': push_data['tag']
        }

        try:
            event_payload['scale_config'] = self.fetch_image_config(event_payload['full_image_id'])
        except docker.errors.DockerException:
            logger.exception("error while fetching image config for %s" %
                             event_payload['full_image_id'])

        self.dispatch('image_updated', event_payload)
        logger.debug("dispatching %s", event_payload)

    def _build_service_stat(self, service):
        """
        build the service stats with the folowing values :

        - name: name of the service
        - image: the name of the image
        - tag: the versio of the image
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
            'tag': image_data['tag'],
            'repository': image_data['repository'],
            'digest': image_data['digest'],
            'ports': [
                {'published': d['PublishedPort'],
                 'target': d['TargetPort']
                 } for d in service.attrs['Endpoint'].get('Ports', ())
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
            'tag': image_data['tag'],
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
