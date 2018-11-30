import json
import logging
import unittest
from unittest import mock

import eventlet.greenpool
from docker.client import DockerClient
from nameko.testing.services import worker_factory

from service.scaler_docker.scaler_docker import ScalerDocker

logger = logging.getLogger(__name__)


class ScalerDockerTestCase(unittest.TestCase):
    EVENT_FIXTURE = {
        "events": [
            {
                "id": "269b7346-dc07-45cd-ad9e-bb9d6d7c532c",

                "timestamp": "2017-05-02T15:20:42.909063631Z",
                "action": "push",
                "target": {

                    "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "size": 1777,
                    "digest": "sha256:11756e3866c185aa3cc5fa77b912456da847d276e3d55c50eabc6421612a2a1f",
                    "length": 1777,
                    "repository": "nginx",
                    "url": "http://localdocker:5000/v2/nginx/manifests/sha256:11756e3866c185aa3cc5fa77b912456da847d"
                           "276e3d55c50eabc6421612a2a1f",
                    "tag": "test"},
                "request": {
                    "id": "7c5ad739-5417-4907-82ad-97eceae39bd3",
                    "addr": "192.168.1.141:36992",
                    "host": "localdocker:5000",
                    "method": "PUT",
                    "useragent":
                        "docker/17.03.1-ce go/go1.7.5 git-commit/c6d412e kernel/4.9.0-2-amd64 os/linux arch/amd64 "
                        "UpstreamClient(Docker-Client/17.03.1-ce \\(linux\\))"},
                "actor": {},
                "source": {

                    "addr": "56f6bdea85c0:5000",
                    "instanceID": "cac5f87b-8e5b-41cc-9207-c32fd38844a4"}
            }
        ]
    }

    DOCKERHUB_EVENT_FIXTURE = {
        "push_data": {"pushed_at": 1496845658, "images": [], "tag": "scaler_docker-1.0.2", "pusher": "yupeek"},
        "callback_url": "https://registry.hub.docker.com/u/yupeek/maiev/hook/25h2cb4chfgfb4f45eaf1cf0354ddafj2/",
        "repository": {"status": "Active", "description": "all docker image for the maiev micro-service ochestrator",
                       "is_trusted": False,
                       "full_description": "Maiev is a ochestrator for micro-service.\n\nit's a set of micro-service "
                                           "that monitor, scale and upgrade automaticaly based on information given "
                                           "by the micro-service itself.\n\nsee the gitub page : "
                                           "https://github.com/Yupeek/maiev",
                       "repo_url": "https://hub.docker.com/r/yupeek/maiev", "owner": "yupeek", "is_official": False,
                       "is_private": False, "name": "maiev", "namespace": "yupeek", "star_count": 0,
                       "comment_count": 0, "date_created": 1494921366, "repo_name": "yupeek/maiev"}}

    def test_push_notification(self):
        pool = eventlet.greenpool.GreenPool(1)
        fake_provider = mock.MagicMock(DockerClient)
        fake_provider.containers.run.return_value.logs.return_value = b'{}'

        service = worker_factory(ScalerDocker, pool=pool, docker=fake_provider)  # type: ScalerDocker
        request = mock.Mock()
        request.get_data = lambda as_text: json.dumps(self.EVENT_FIXTURE)

        service.event(request)
        pool.waitall()
        service.dispatch.assert_called_once_with(
            'image_updated',
            {
                'from': 'scaler_docker',
                'scale_config': {},
                'tag': 'test',
                'full_image_id': 'localdocker:5000/nginx@sha256:11756e3866c185aa3cc5fa77b912456da8'
                                 '47d276e3d55c50eabc6421612a2a1f',
                'image': 'nginx',
                'repository': 'localdocker:5000',
                'digest': 'sha256:11756e3866c185aa3cc5fa77b912456da847d276e3d55c50eabc6421612a2a1f'
            }
        )

    def test_push_notification_from_hub(self):
        pool = eventlet.greenpool.GreenPool(1)
        fake_provider = mock.MagicMock(DockerClient)
        fake_provider.containers.run.return_value.logs.return_value = b'{}'

        service = worker_factory(ScalerDocker, pool=pool, docker=fake_provider)  # type: ScalerDocker
        request = mock.Mock()
        request.get_data = lambda as_text: json.dumps(self.DOCKERHUB_EVENT_FIXTURE)

        service.event(request)
        pool.waitall()
        service.dispatch.assert_called_once_with(
            'image_updated',
            {
                'from': 'scaler_docker',
                'scale_config': {},
                'tag': 'scaler_docker-1.0.2',
                'full_image_id': 'yupeek/maiev:scaler_docker-1.0.2',
                'image': 'maiev',
                'repository': 'yupeek',
                'digest': None
            }
        )

    def test_fetch_scale_config(self):
        fake_provider = mock.MagicMock(DockerClient)
        fake_provider.containers.run.return_value.logs.return_value = b'{}'

        service = worker_factory(ScalerDocker, docker=fake_provider)  # type: ScalerDocker
        service.fetch_image_config('nginx')
        fake_provider.containers.run.assert_called_once_with('nginx', 'scale_info', remove=False, detach=True)

    def test_bad_scale_config(self):
        fake_provider = mock.MagicMock(DockerClient)
        fake_provider.containers.run.return_value.logs.return_value = b'{'

        service = worker_factory(ScalerDocker, docker=fake_provider)  # type: ScalerDocker
        with self.assertLogs(None, 'ERROR'):
            res = service.fetch_image_config('nginx')
        self.assertIsNone(res)
