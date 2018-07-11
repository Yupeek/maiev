# -*- coding: utf-8 -*-
import copy
import logging
from unittest import mock
from unittest.case import TestCase, skip

import pytest
from bson import ObjectId
from nameko.testing.services import worker_factory

from common.utils import filter_dict
from service.overseer.overseer import Overseer

logger = logging.getLogger(__name__)


class TestOverseerUpdateImage(TestCase):
    update_payload = {
        'from': 'scaler_docker',
        'scale_config': {},
        'tag': 'producer-1.1',
        'full_image_id': 'localhost:5000/maiev:producer-1.1@sha256:'
                         'e033d82c4889959f6557f1be99014c2a4001ee38dee71fb2c8abc47d3acba34e',
        'repository': 'localhost:5000',
        'image': 'maiev',
        'digest': 'sha256:e033d82c4889959f6557f1be99014c2a4001ee38dee71fb2c8abc47d3acba34e'
    }

    SERVICE_SAMPLE = {
        'image': {'full_image_id': 'localhost:5000/maiev:producer',
                  'image_info': {'digest': None,
                                 'image': 'maiev',
                                 'repository': 'localhost:5000',
                                 'species': 'producer',
                                 'tag': 'producer-1.0',
                                 'version': '1.0'},
                  'type': 'docker'},
        'mode': {'name': 'replicated', 'replicas': 0},
        'name': 'producer',
        'scale_config': None,
        'start_conig': {'env': {}, 'secret': []}
    }

    def test_unknown_image(self):
        overseer = worker_factory(Overseer)
        overseer.mongo.services.find.return_value = []
        with mock.patch.object(overseer, '_update_service') as _update_service:
            overseer.on_image_updated(self.update_payload)
            self.assertFalse(_update_service.called)

    @skip
    def test_known_image(self):
        overseer = worker_factory(Overseer)
        overseer.mongo.services.find.return_value = [self.SERVICE_SAMPLE]
        with mock.patch.object(overseer, '_update_service') as _update_service:
            overseer.on_image_updated(self.update_payload)
            _update_service.assert_called_once_with(self.SERVICE_SAMPLE,
                                                    image_id='localhost:5000/maiev:producer-1.1@sha256:e033d82c48899'
                                                             '59f6557f1be99014c2a4001ee38dee71fb2c8abc47d3acba34e')

    def test_version_backward(self):
        overseer = worker_factory(Overseer)
        service = copy.deepcopy(self.SERVICE_SAMPLE)
        service['image']['image_info']['version'] = '1.2'
        service['image']['image_info']['tag'] = 'producer-1.2'
        overseer.mongo.services.find.return_value = [service]
        with mock.patch.object(overseer, '_update_service') as _update_service:
            overseer.on_image_updated(self.update_payload)
            self.assertFalse(_update_service.called)


@pytest.fixture
def overseer(service):
    o = Overseer()
    o.dispatch = mock.Mock()
    o.scaler_docker = mock.Mock()
    o.mongo = mock.Mock()
    o.scaler_docker.fetch_image_config.return_value = service['scale_config']
    return o


@pytest.fixture
def service_data():
    return {
        'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
        'envs': {'RABBITMQ_HOST': 'rabbitmq', 'TOTO': 'titi'},
        'full_image_id': 'localhost:5000/maiev:producer-1.0.16@'
                         'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
        'image': 'maiev',
        'instances': [{'image': 'maiev',
                       'is_running': True,
                       'repository': 'localhost:5000',
                       'tag': 'producer-1.0.16',
                       'updated_at': '2018-04-30T08:59:46.7383385Z'},
                      {'image': 'maiev',
                       'is_running': True,
                       'repository': 'localhost:5000',
                       'tag': 'producer-1.0.16',
                       'updated_at': '2018-04-30T08:59:46.738425887Z'}],
        'mode': {'name': 'replicated', 'replicas': 0},
        'name': 'producer',
        'ports': [],
        'repository': 'localhost:5000',
        'tag': 'producer-1.0.16'}


@pytest.fixture
def service():
    return {
        '_id': ObjectId('5ae6d604650fad823226f669'),
        'image': {'full_image_id': 'localhost:5000/maiev:producer',
                  'image_info': {
                      'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
                      'image': 'maiev',
                      'repository': 'localhost:5000',
                      'species': 'producer',
                      'tag': 'producer-1.0.16',
                      'version': '1.0.16'},
                  'type': 'docker'},
        'latest_ruleset': {},
        'mode': {'name': 'replicated', 'replicas': 0},
        'name': 'producer',
        'scale_config': {'dependencies': {'optional': [], 'required': []},
                         'max': 9,
                         'min': 0,
                         'scale': {'resources': [{'identifier': 'rpc-producer',
                                                  'monitorer': 'monitorer_rabbitmq',
                                                  'name': 'rmq'}],
                                   'rules': [{'expression': 'rmq:waiting == 0 or '
                                                            'rmq:latency < 0.200',
                                              'name': 'latency_ok'},
                                             {'expression': 'rmq:latency > 5',
                                              'name': 'latency_fail'},
                                             {'expression': 'rmq:latency > 10 or '
                                                            '(rules:latency_fail and '
                                                            'rules:latency_fail:since '
                                                            '> "25s")',
                                              'name': 'panic'},
                                             {'expression': 'rules:latency_ok and '
                                                            'rules:latency_ok:since > '
                                                            '"30s"',
                                              'name': 'stable_latency'}],
                                   'scale_down': 'rules:stable_latency',
                                   'scale_up': 'rules:panic or (rmq:consumers == 0 '
                                               'and rmq:waiting > 0)'}},
        'start_conig': {'env': {}, 'secret': []}}


class TestServiceUpdatePropagation(object):

    def test_diff_compute_no_diff(self, overseer: Overseer, service_data, service):
        d = overseer._compute_diff(service_data, service, {})
        assert d == {}

    def test_diff_with_image(self, overseer: Overseer, service_data, service):
        service_data['tag'] = 'producer-1.0.18'
        d = overseer._compute_diff(service_data, service, {})
        assert {'image'} == set(d)
        assert d['image'] == {
            'from':
                {'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
                 'image': 'maiev',
                 'repository': 'localhost:5000',
                 'species': 'producer',
                 'tag': 'producer-1.0.16',
                 'version': '1.0.16'},
            'to': {'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
                   'image': 'maiev',
                   'repository': 'localhost:5000',
                   'species': 'producer',
                   'tag': 'producer-1.0.18',
                   'version': '1.0.18'},
        }

    def test_diff_with_scale(self, overseer: Overseer, service_data, service):
        service_data['mode']['replicas'] = 10
        d = overseer._compute_diff(service_data, service, {})
        assert {'scale'} == set(d)
        assert d['scale'] == {'from': 0, 'to': 10}

    def test_diff_with_mode(self, overseer: Overseer, service_data, service):
        service_data['mode']['name'] = 'global'
        d = overseer._compute_diff(service_data, service, {})
        assert {'mode'} == set(d)
        assert d['mode'] == {'from': {'name': 'replicated', 'replicas': 0}, 'to': {'name': 'global', 'replicas': 0}}

    def test_diff_with_new_status_attrs_no_old(self, overseer: Overseer, service_data, service):
        d = overseer._compute_diff(service_data, service, {
            "updatestate.new": 'completed'
        })
        assert {'state'} == set(d)
        assert d['state'] == {'from': None, 'to': 'completed'}

    def test_diff_with_new_status_attrs(self, overseer: Overseer, service_data, service):
        d = overseer._compute_diff(service_data, service, {
            "updatestate.new": 'completed',
            "updatestate.old": 'upgrading'
        })
        assert {'state'} == set(d)
        assert d['state'] == {'from': 'upgrading', 'to': 'completed'}


class TestOverseerServiceEvent(object):
    DIFF_IMAGE = {'image': {
        'from':
            {'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
             'image': 'maiev',
             'repository': 'localhost:5000',
             'species': 'producer',
             'tag': 'producer-1.0.16',
             'version': '1.0.16'},
        'to': {'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
               'image': 'maiev',
               'repository': 'localhost:5000',
               'species': 'producer',
               'tag': 'producer-1.0.18',
               'version': '1.0.18'},
    }}

    def test_event_service_updated_no_diff(self, overseer: Overseer, service_data, service):
        overseer.mongo.services.find_one.return_value = service
        overseer.on_service_updated({'service': service_data, 'attributes': {}})
        overseer.dispatch.assert_not_called()

    def test_event_service_updated_with_diff(self, overseer: Overseer, service_data, service):
        overseer.mongo.services.find_one.return_value = service
        service_data['tag'] = 'producer-1.0.18'
        overseer.on_service_updated({'service': service_data, 'attributes': {}})
        overseer.dispatch.assert_called_once_with('service_updated', {
            'service': filter_dict(service),
            'diff': self.DIFF_IMAGE})

    def test_event_service_updated_scale(self, overseer: Overseer, service):
        overseer.check_new_scale_config({'diff': {'scale': {'from': 0, 'to': 10}}, 'service': filter_dict(service)})
        overseer.mongo.services.update_one.assert_not_called()
        overseer.dispatch.assert_not_called()

    def test_event_service_updated_image_same_config(self, overseer: Overseer, service):
        overseer.check_new_scale_config({'diff': self.DIFF_IMAGE, 'service': filter_dict(service)})
        overseer.mongo.services.update_one.assert_not_called()
        overseer.dispatch.assert_not_called()

    def test_event_service_updated_image_updated_config(self, overseer: Overseer, service):
        scale_config = copy.deepcopy(service['scale_config'])
        scale_config['max'] = 4
        overseer.scaler_docker.fetch_image_config.return_value = scale_config
        overseer.check_new_scale_config({'diff': self.DIFF_IMAGE, 'service': filter_dict(service)})
        overseer.mongo.services.update_one.assert_called()
        overseer.dispatch.assert_called()

    def test_new_image_notified(self, overseer: Overseer, service):
        overseer.mongo.services.find.return_value = [service]
        overseer.on_image_updated({
            'from': 'scaler_docker',
            'digest': 'sha256:aaa',
            'image': 'maiev',
            'repository': 'localhost:5000',
            'tag': 'consumer-1.0.1',
            'full_image_id': 'localhost:5000/maiev@sha256:aaa',
            'scale_config': None
        })
        overseer.dispatch.assert_called_with('new_image', {
            "service": filter_dict(service),
            "image": {'repository': 'localhost:5000',
                      'image': 'maiev',
                      'tag': 'consumer-1.0.1',
                      'species': 'consumer',
                      'version': '1.0.1',
                      'digest': 'sha256:aaa'},
            "scale_config": service['scale_config']
        })

    def test_new_image_notified_not_monitored(self, overseer: Overseer, service):
        overseer.mongo.services.find.return_value = []
        overseer.on_image_updated({
            'from': 'scaler_docker',
            'digest': 'sha256:aaa',
            'image': 'maiev',
            'repository': 'localhost:5000',
            'tag': 'consumer-1.0.1',
            'full_image_id': 'localhost:5000/maiev@sha256:aaa',
            'scale_config': None
        })
        overseer.dispatch.assert_not_called()


class TestRecheck:

    def test_all_known_versions(self, overseer: Overseer, service_data, service):
        overseer.mongo.versions.find.return_value = [
            {'digest': 'sha256:40c6c8b1a244746d4c351f9079848cf6325342a9023b8bf143a59201b8e0b789',
             'image': 'maiev',
             'repository': 'localhost:5000',
             'species': 'consumer',
             'tag': 'consumer-1.0.1',
             'version': '1.0.1'},
            {'digest': 'lolilol',
             'image': 'maiev',
             'repository': 'localhost:5000',
             'species': 'producer',
             'tag': 'producer-1.0.1',
             'version': '1.0.1'},
        ]
        overseer.scaler_docker.list_tags.return_value = ['consumer-1.0.1', 'producer-1.0.1']
        overseer.mongo.services.find.return_value = [service]
        overseer.recheck_new_version()
        overseer.dispatch.assert_not_called()
        overseer.mongo.version.insert.assert_not_called()
        overseer.mongo.version.remove.assert_not_called()

    def test_cleaned_version(self, overseer: Overseer, service_data, service):
        overseer.mongo.versions.find.return_value = [
            {'digest': 'sha256:40c6c8b1a244746d4c351f9079848cf6325342a9023b8bf143a59201b8e0b789',
             'image': 'maiev',
             'repository': 'localhost:5000',
             'species': 'consumer',
             'tag': 'consumer-1.0.1',
             'version': '1.0.1',
             '_id': 'abcdef'},
            {'digest': 'lolilol',
             'image': 'maiev',
             'repository': 'localhost:5000',
             'species': 'producer',
             'tag': 'producer-1.0.1',
             'version': '1.0.1',
             '_id': 'abcdef'
             },
        ]
        overseer.scaler_docker.list_tags.return_value = ['consumer-1.0.1']
        overseer.mongo.services.find.return_value = [service]
        overseer.recheck_new_version()
        overseer.dispatch.assert_called_once_with('cleaned_image', {
            "service": filter_dict(service),
            'image': {
                'digest': 'lolilol',
                'image': 'maiev',
                'repository': 'localhost:5000',
                'species': 'producer',
                'tag': 'producer-1.0.1',
                'version': '1.0.1'
            }
        })
        overseer.mongo.versions.remove.assert_called_with({
            '_id': 'abcdef'

        })

    def test_new_version(self, overseer: Overseer, service_data, service):
        overseer.mongo.versions.find.return_value = [
            {'digest': 'sha256:40c6c8b1a244746d4c351f9079848cf6325342a9023b8bf143a59201b8e0b789',
             'image': 'maiev',
             'repository': 'localhost:5000',
             'species': 'producer',
             'tag': 'producer-1.0.1',
             'version': '1.0.1'}
        ]
        overseer.scaler_docker.list_tags.return_value = ['producer-1.0.1', 'producer-1.0.2']
        overseer.mongo.services.find.return_value = [service]
        overseer.recheck_new_version()
        overseer.dispatch.assert_called_with('new_image', {
            "service": filter_dict(service),
            "image": {'repository': 'localhost:5000',
                      'image': 'maiev',
                      'tag': 'producer-1.0.2',
                      'species': 'producer',
                      'version': '1.0.2',
                      'digest': None},
            "scale_config": service['scale_config']
        })
        overseer.mongo.versions.insert.assert_called_with({
            'repository': 'localhost:5000',
            'image': 'maiev',
            'tag': 'producer-1.0.2',
            'species': 'producer',
            'version': '1.0.2',
            'digest': None})
