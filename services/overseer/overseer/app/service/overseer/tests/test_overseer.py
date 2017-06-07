# -*- coding: utf-8 -*-
import copy
import logging
from unittest import mock
from unittest.case import TestCase

from nameko.testing.services import worker_factory
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
