# -*- coding: utf-8 -*-
import logging
from unittest.case import TestCase

from common.utils import ImageVersion

logger = logging.getLogger(__name__)


class TestImageVersion(TestCase):
    def assert_parsed_equal(self, *hints, **result):
        """
        helper to check if the given hints result in the good parsed.
        hint should be a tuple starting with the tag > image > repository > digest.
        all missed part will be defaulted.
        :param hints:
        :param result:
        :return:
        """
        iv = self.create_iv(*hints)
        self.assertEqual({k: v for k, v in iv.data.items() if k in result}, result)

    def create_iv(self, *hints):
        final_hints = {
            'tag': 'latest',
            'image': 'maiev',
            'repository': 'hub.docker.com',
            'digest': 'sha256:0870f'
        }

        final_hints.update(dict(zip(('tag', 'image', 'repository', 'digest'), hints)))
        return ImageVersion.from_scaler(final_hints)

    def test_tostring(self):
        self.assertEqual(str(self.create_iv(
            'alpine', 'python', 'localhost', 'aaaaaa'
        )), 'ImageVersion localhost/python:alpine version=None')
        self.assertEqual(str(self.create_iv(
            'overseer-1.2.78', 'maiev', 'localhost', 'bbbbb'
        )), 'ImageVersion localhost/maiev:overseer version=1.2.78')

    def test_torepr(self):
        self.assertEqual(repr(self.create_iv(
            'alpine', 'python', 'localhost', 'aaaaaa'
        )), '<ImageVersion localhost/python:alpine version=None>')
        self.assertEqual(repr(self.create_iv(
            'overseer-1.2.78', 'maiev', 'localhost', 'bbbbb'
        )), '<ImageVersion localhost/maiev:overseer version=1.2.78>')

    def test_parse_versions(self):
        # public repo
        self.assert_parsed_equal('3.6.1', version="3.6.1", species=None)
        self.assert_parsed_equal('3.6', version="3.6", species=None)
        self.assert_parsed_equal('3', version="3", species=None)
        self.assert_parsed_equal('latest', version="latest", species=None)
        self.assert_parsed_equal('3.6.1-slim_lol', version="3.6.1", species='slim_lol')
        self.assert_parsed_equal('3.6-slim_lol', version="3.6", species='slim_lol')
        self.assert_parsed_equal('3-slim_lol', version="3", species='slim_lol')
        self.assert_parsed_equal('slim_lol', version=None, species='slim_lol')
        self.assert_parsed_equal('3.6.1-alpine', version="3.6.1", species='alpine')
        self.assert_parsed_equal('3.6-alpine', version="3.6", species='alpine')
        self.assert_parsed_equal('3-alpine', version="3", species='alpine')
        self.assert_parsed_equal('alpine', version=None, species='alpine')
        self.assert_parsed_equal('', version=None, species=None)
        # private version
        self.assert_parsed_equal('overseer-1.0.69', version="1.0.69", species='overseer')
        self.assert_parsed_equal('overseer-latest', version="latest", species='overseer')
        self.assert_parsed_equal('scaler_docker-1.0', version="1.0", species='scaler_docker')
        self.assert_parsed_equal('scaler_docker', version=None, species='scaler_docker')
        # private advanced
        self.assert_parsed_equal('overseer-1.0.69a1+build45', version="1.0.69a1+build45", species='overseer')
        self.assert_parsed_equal('overseer-1.0.69a1', version="1.0.69a1", species='overseer')
        self.assert_parsed_equal('overseer-1.0.69+build43', version="1.0.69+build43", species='overseer')

    def test_full_parse(self):
        self.assert_parsed_equal('alpine', 'python', 'localhost', version=None, image='python',
                                 species='alpine', repository='localhost')
        self.assert_parsed_equal('3.6.1-alpine', 'python', 'localhost', version='3.6.1', image='python',
                                 species='alpine', repository='localhost', tag='3.6.1-alpine')
        self.assert_parsed_equal('overseer', 'maiev', 'localhost', version=None, image='maiev',
                                 species='overseer', repository='localhost')
        self.assert_parsed_equal('overseer-1.0.68', 'maiev', 'localhost', version='1.0.68', image='maiev',
                                 species='overseer', repository='localhost', tag='overseer-1.0.68')

    def test_get_id(self):
        self.assertEqual(self.create_iv('alpine', 'python', 'localhost').image_id,
                         'localhost/python:alpine')
        self.assertEqual(self.create_iv('3.6.1-alpine', 'python', 'localhost').image_id,
                         'localhost/python:alpine')
        self.assertEqual(self.create_iv('overseer', 'maiev', 'localhost').image_id,
                         'localhost/maiev:overseer')
        self.assertEqual(self.create_iv('overseer-1.0.68', 'maiev', 'localhost').image_id,
                         'localhost/maiev:overseer')

    def test_get_unique_image_id(self):
        self.assertEqual(self.create_iv('alpine', 'python', 'localhost').unique_image_id,
                         'localhost/python:alpine@sha256:0870f')
        self.assertEqual(self.create_iv('3.6.1-alpine', 'python', 'localhost').unique_image_id,
                         'localhost/python:3.6.1-alpine@sha256:0870f')
        self.assertEqual(self.create_iv('overseer', 'maiev', 'localhost').unique_image_id,
                         'localhost/maiev:overseer@sha256:0870f')
        self.assertEqual(self.create_iv('overseer-1.0.68', 'maiev', 'localhost').unique_image_id,
                         'localhost/maiev:overseer-1.0.68@sha256:0870f')

    def test_with_more_data_than_needed(self):
        # simulate the return data from a scaler on update
        data = {'name': 'producer',
                'full_image_id': 'localhost:5000/maiev:producer-1.0.1@sha256:0870f704422986756864f0b189'
                                 'abafd2f70f6c1b30edd9a3654be2060baf2dfc',
                'image': 'maiev', 'tag': 'producer-1.0.1', 'repository': 'localhost:5000', 'ports': [],
                'digest': 'sha256:0870f704422986756864f0b189abafd2f70f6c1b30edd9a3654be2060baf2dfc',
                'instances': [], 'envs': {}, 'mode': {'name': 'replicated', 'replicas': 0}}
        iv = ImageVersion.from_scaler(data)
        self.assertEqual(iv.unique_image_id, 'localhost:5000/maiev:producer-1.0.1@sha256:0870f704422986756864f0b189'
                                             'abafd2f70f6c1b30edd9a3654be2060baf2dfc')
        self.assertEqual(iv.image_id, 'localhost:5000/maiev:producer')

    def test_equality(self):
        self.assertEqual(
            self.create_iv('alpine', 'python'),
            self.create_iv('alpine', 'python')
        )
        self.assertNotEqual(
            self.create_iv('alpine', 'python'),
            self.create_iv('3-alpine', 'python')
        )
        self.assertNotEqual(
            self.create_iv('alpine', 'python'),
            self.create_iv('alpine', 'maiev')
        )
        self.assertNotEqual(
            self.create_iv('alpine', 'python', 'localhost'),
            self.create_iv('alpine', 'python', 'hub.docker.com')
        )

    def test_inequality_ok(self):
        self.assertTrue(
            self.create_iv('3.1') < self.create_iv('3.2')
        )
        self.assertTrue(
            self.create_iv('3.2') > self.create_iv('3.1')
        )
        self.assertTrue(
            self.create_iv('3.1-alpine') < self.create_iv('3.2-alpine')
        )
        self.assertTrue(
            self.create_iv('3.2-alpine') > self.create_iv('3.1-alpine')
        )
        self.assertTrue(
            self.create_iv('3') < self.create_iv('3.2')
        )
        self.assertTrue(
            self.create_iv('3.2') > self.create_iv('3')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.47') < self.create_iv('overseer-3.1.76')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.76') > self.create_iv('overseer-3.1.46')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.9') < self.create_iv('overseer-3.1.76')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.76') > self.create_iv('overseer-3.1.9')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.9a1') < self.create_iv('overseer-3.1.76')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.76') > self.create_iv('overseer-3.1.9a1')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.76') > self.create_iv('overseer-3.1.76a1')
        )
        self.assertTrue(
            self.create_iv('overseer-3.1.76b1') > self.create_iv('overseer-3.1.76a7')
        )
        self.assertFalse(
            self.create_iv('overseer-3.1.9+build1') < self.create_iv('overseer-3.1.9')
        )
        self.assertFalse(
            self.create_iv('overseer-3.1.9+build1') > self.create_iv('overseer-3.1.9')
        )

    def test_latest_equality(self):
        # the default behavior is to treat latest tages as special version
        # latest use digest to compare version
        self.assertEqual(
            self.create_iv('latest', 'maiev', 'localhost', 'aaaaaaaaaa'),
            self.create_iv('latest', 'maiev', 'localhost', 'aaaaaaaaaa'),
        )
        self.assertNotEqual(
            self.create_iv('latest', 'maiev', 'localhost', 'aaaaaaaaaa'),
            self.create_iv('latest', 'maiev', 'localhost', 'bbbbbbbbbb'),
        )
        self.assertNotEqual(
            self.create_iv('latest', 'maiev', 'localhost', 'aaaaaaaaaa'),
            self.create_iv('1.0', 'maiev', 'localhost', 'aaaaaaaaaa'),
        )

    def test_latest_inequality(self):
        # the default behavior is to treat latest tages as special version
        # latest is alwayes newer than any other (including latest)

        self.assertFalse(
            self.create_iv('latest') < self.create_iv('latest')
        )
        self.assertTrue(
            self.create_iv('latest') > self.create_iv('latest')
        )
        self.assertTrue(
            self.create_iv('9999') < self.create_iv('latest')
        )
        self.assertTrue(
            self.create_iv('latest') > self.create_iv('9999')
        )

    def test_inequality_bad_image(self):
        self.assertFalse(
            self.create_iv('overseer') > self.create_iv('trigger')
        )
        self.assertFalse(
            self.create_iv('overseer') < self.create_iv('trigger')
        )
        self.assertFalse(
            self.create_iv('overseer-3.1.76') > self.create_iv('trigger')
        )
        self.assertFalse(
            self.create_iv('overseer-3.1.76') < self.create_iv('trigger')
        )
        self.assertFalse(
            self.create_iv('overseer', 'maiev') > self.create_iv('overseer', 'ganymede')
        )
        self.assertFalse(
            self.create_iv('overseer', 'maiev') < self.create_iv('overseer', 'ganymede')
        )
        self.assertFalse(
            self.create_iv('overseer', 'maiev', 'localhost') > self.create_iv('overseer', 'maiev', 'hub.docker.com')
        )
        self.assertFalse(
            self.create_iv('overseer', 'maiev', 'localhost') < self.create_iv('overseer', 'maiev', 'hub.docker.com')
        )
