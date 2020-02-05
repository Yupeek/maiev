# -*- coding: utf-8 -*-
import json
import logging
import os
from functools import reduce

import mock
# other MS
import pytest

from service.upgrade_planer.upgrade_planer import ACCEPT_ALL, NO_DOWNGRADE, Phase, PhasePin, UpgradePlaner

logger = logging.getLogger(__name__)


@pytest.fixture
def event_payload():
    return {'image': {'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                      'image': 'maiev',
                      'repository': 'localhost:5000',
                      'species': 'producer',
                      'tag': 'producer-1.0.1',
                      'version': '1.0.1'},
            'scale_config': {'dependencies': {'provide': [], 'require': []},
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
                                                                'rules:latency_ok:since '
                                                                '> "30s"',
                                                  'name': 'stable_latency'}],
                                       'scale_down': 'rules:stable_latency and '
                                                     'rmq:consumers > 0',
                                       'scale_up': 'rules:panic or (rmq:consumers == 0 '
                                                   'and rmq:waiting > 0) or not '
                                                   'rmq:exists'}},
            'service': {'image': {'full_image_id': 'localhost:5000/maiev:producer',
                                  'image_info': {
                                      'digest': 'sha256:581647ffd59fc7dc9b2f164fe299d'
                                                'e29bf99fb1cb304c41ea07d8fa3f95f052b',
                                      'image': 'maiev',
                                      'repository': 'localhost:5000',
                                      'species': 'producer',
                                      'tag': 'producer-1.0.16',
                                      'version': '1.0.16'},
                                  'type': 'docker'},
                        'latest_ruleset': {},
                        'mode': {'name': 'replicated', 'replicas': 23},
                        'name': 'producer',
                        'scale_config': None,
                        'start_config': {'env': {}, 'secret': []}}}


@pytest.fixture
def service():
    return {
        "consumer": {'image': {'full_image_id': 'localhost:5000/maiev:consumer',
                               'image_info': {
                                   'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
                                   'image': 'maiev',
                                   'repository': 'localhost:5000',
                                   'species': 'consumer',
                                   'tag': 'consumer-1.0.16',
                                   'version': '1.0.16'},
                               'type': 'docker'},
                     'latest_ruleset': {},
                     'mode': {'name': 'replicated', 'replicas': 23},
                     'name': 'consumer',
                     'scale_config': None,
                     'start_config': {'env': {}, 'secret': []}},
        "producer": {'image': {'full_image_id': 'localhost:5000/maiev:producer',
                               'image_info': {
                                   'digest': 'sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b',
                                   'image': 'maiev',
                                   'repository': 'localhost:5000',
                                   'species': 'producer',
                                   'tag': 'producer-1.0.16',
                                   'version': '1.0.16'},
                               'type': 'docker'},
                     'latest_ruleset': {},
                     'mode': {'name': 'replicated', 'replicas': 23},
                     'name': 'producer',
                     'scale_config': None,
                     'start_config': {'env': {}, 'secret': []}}
    }


@pytest.fixture
def catalog(service):
    return [{
        "name": "consumer",
        "service": service['consumer'],
        "versions_list": [
            {"version": "1.0.16", "dependencies": {
                "require": [
                    "producer:rpc:echo"
                ]
            }}],

        "version": service['consumer']['image']['image_info']['version'],
    }, {
        "name": "producer",
        "service": service['producer'],
        "versions_list": [
            {"version": "1.0.16", "dependencies": {
                "provide": {
                    "producer:rpc:echo": 1
                }}}
        ],
        "version": service['producer']['image']['image_info']['version'],

    }
    ]


@pytest.fixture
def upgrade_planer():
    service = UpgradePlaner()
    service.config = {}
    service.mongo = mock.Mock()
    service.dispatch = mock.Mock()
    service.dependency_solver = mock.Mock()
    return service


class TestUpgradePlaner(object):

    def test_update_catalog_new_service(self, event_payload, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find_one.return_value = None
        upgrade_planer.on_new_version(event_payload)
        new_version = {
            "version": "1.0.1",
            "dependencies": event_payload['scale_config']['dependencies'],
            "image_info": {
                'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                'image': 'maiev',
                'repository': 'localhost:5000',
                'species': 'producer',
                'tag': 'producer-1.0.1',
                'version': '1.0.1'
            },
            "available": True
        }
        upgrade_planer.dispatch.assert_called_with(
            "new_version",
            {
                "service": {
                    "name": "producer",
                    "service": event_payload['service'],
                    "versions": {
                        "1.0.1": new_version
                    },
                    "version": event_payload['service']['image']['image_info']['version'],

                },
                "new": new_version
            })

    def test_update_catalog_existing_version(self, event_payload, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find_one.return_value = {
            "name": "producer",
            "service": event_payload['service'],
            "versions_list": [{
                "version": "1.0.1",
                "dependencies": event_payload['scale_config']['dependencies'],
                "image_info": {
                    'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                    'image': 'maiev',
                    'repository': 'localhost:5000',
                    'species': 'producer',
                    'tag': 'producer-1.0.1',
                    'version': '1.0.1'
                },
                "available": True
            }
            ],
        }
        upgrade_planer.on_new_version(event_payload)
        upgrade_planer.dispatch.assert_not_called()

    def test_update_catalog_new_image(self, event_payload, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find_one.return_value = {
            "name": "producer",
            "service": event_payload['service'],
            "versions_list": [{
                "version": "1.0.0",
                "dependencies": {},
                "image_info": {
                    'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                    'image': 'maiev',
                    'repository': 'localhost:5000',
                    'species': 'producer',
                    'tag': 'producer-1.0.0',
                    'version': '1.0.0'
                },
                "available": True

            }],
        }
        upgrade_planer.on_new_version(event_payload)
        new_version = {"version": "1.0.1",
                       "dependencies": event_payload['scale_config']['dependencies'],
                       "image_info": {
                           'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                           'image': 'maiev',
                           'repository': 'localhost:5000',
                           'species': 'producer',
                           'tag': 'producer-1.0.1',
                           'version': '1.0.1'
                       },
                       "available": True
                       }
        upgrade_planer.dispatch.assert_called_with(
            "new_version",
            {
                "service": {
                    "name": "producer",
                    "service": event_payload['service'],
                    "versions": {
                        "1.0.0": {
                            "version": "1.0.0",
                            "dependencies": {},
                            "image_info": {
                                'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                                'image': 'maiev',
                                'repository': 'localhost:5000',
                                'species': 'producer',
                                'tag': 'producer-1.0.0',
                                'version': '1.0.0'
                            },
                            "available": True
                        },
                        "1.0.1": new_version
                    },
                },
                "new": new_version
            })

    def test_build_catalog(self, upgrade_planer: UpgradePlaner, service):
        upgrade_planer.mongo.catalog.find.return_value = [{
            "name": "consumer",
            "service": service['consumer'],
            "versions_list": [
                {"version": "1.0.16", "dependencies": {
                    "require": [
                        "producer:rpc:echo"
                    ]
                }}],

            "version": service['consumer']['image']['image_info']['version'],
        }, {
            "name": "producer",
            "service": service['producer'],
            "versions_list": [
                {"version": "1.0.16", "dependencies": {
                    "provide": {
                        "producer:rpc:echo": 1
                    }}}
            ],
            "version": service['producer']['image']['image_info']['version'],

        }
        ]
        c = upgrade_planer.build_catalog()
        assert c == [
            {
                "name": "consumer",
                "versions": {
                    "1.0.16": {
                        "provide": {},
                        "require": ["producer:rpc:echo"]
                    },
                }
            },
            {
                "name": "producer",
                "versions": {
                    "1.0.16": {
                        "provide": {
                            "producer:rpc:echo": 1
                        },
                        "require": []
                    },
                }
            }
        ]

    def test_build_catalog_beta_versions(self, upgrade_planer: UpgradePlaner, service):
        service['consumer']['image']['image_info']['version'] = '1.0.16b'
        service['producer']['image']['image_info']['version'] = '1.0.16b'
        upgrade_planer.mongo.catalog.find.return_value = [{
            "name": "consumer",
            "service": service['consumer'],
            "versions_list": [
                {"version": "1.0.16b", "dependencies": {
                    "require": [
                        "producer:rpc:echo"
                    ]
                }}],

            "version": service['consumer']['image']['image_info']['version'],
        }, {
            "name": "producer",
            "service": service['producer'],
            "versions_list": [
                {"version": "1.0.16b", "dependencies": {
                    "provide": {
                        "producer:rpc:echo": 1
                    }}}
            ],
            "version": service['producer']['image']['image_info']['version'],

        }
        ]
        c = upgrade_planer.build_catalog()
        assert c == [
            {
                "name": "consumer",
                "versions": {
                    "1.0.16b": {
                        "provide": {},
                        "require": ["producer:rpc:echo"]
                    },
                }
            },
            {
                "name": "producer",
                "versions": {
                    "1.0.16b": {
                        "provide": {
                            "producer:rpc:echo": 1
                        },
                        "require": []
                    },
                }
            }
        ]

    def test_build_catalog_no_solution(self, upgrade_planer: UpgradePlaner, service):
        upgrade_planer.mongo.catalog.find.return_value = [{
            "name": "consumer",
            "service": service['consumer'],
            "versions_list": [
                {"version": "1.0.15", "dependencies": {
                    "require": [
                        "producer:rpc:echo"
                    ]
                }}
            ],
            "version": service['consumer']['image']['image_info']['version']
        }, {
            "name": "producer",
            "service": service['producer'],
            "versions_list": [
                {"version": "1.0.15", "dependencies": {
                    "provide": {
                        "producer:rpc:echo": 1
                    }}}
            ],
            "version": service['producer']['image']['image_info']['version'],
        }
        ]
        c = upgrade_planer.build_catalog(NO_DOWNGRADE)
        assert c == [
            {
                "name": "consumer",
                "versions": {}
            },
            {
                "name": "producer",
                "versions": {}
            }
        ]

    def test_build_catalog_allow_all(self, upgrade_planer: UpgradePlaner, service):
        upgrade_planer.mongo.catalog.find.return_value = [{
            "name": "consumer",
            "service": service['consumer'],
            "versions_list": [
                {"version": "1.0.15", "dependencies": {
                    "require": [
                        "producer:rpc:echo"
                    ]
                }}
            ],
            "version": service['consumer']['image']['image_info']['version'],
        }, {
            "name": "producer",
            "service": service['producer'],
            "versions_list": [
                {"version": "1.0.15", "dependencies": {
                    "provide": {
                        "producer:rpc:echo": 1
                    }}}
            ],
            "version": service['producer']['image']['image_info']['version'],

        }
        ]
        c = upgrade_planer.build_catalog(ACCEPT_ALL)
        assert c == [
            {
                "name": "consumer",
                "versions": {
                    "1.0.15": {
                        "provide": {},
                        "require": ["producer:rpc:echo"]
                    },
                }
            },
            {
                "name": "producer",
                "versions": {
                    "1.0.15": {
                        "provide": {
                            "producer:rpc:echo": 1
                        },
                        "require": []
                    },
                }
            }
        ]

    def test_resolve_upgrade_and_steps_no_goal(self, upgrade_planer: UpgradePlaner, catalog):
        upgrade_planer.build_catalog = mock.Mock(return_value=catalog)
        upgrade_planer.dependency_solver.solve_dependencies = mock.Mock(return_value={
            "results": [{"producer": "1.0.16", "consumer": "1.0.16"}],
            "errors": [],
            "anomalies": []
        })
        bp = Phase([PhasePin(catalog[1], "1.0.16"),
                    PhasePin(catalog[0], "1.0.16")])
        upgrade_planer.solve_best_phase = mock.Mock(return_value=(None, 0))
        upgrade_planer.build_steps = mock.Mock()

        res = upgrade_planer.resolve_upgrade_and_steps()

        upgrade_planer.solve_best_phase.assert_called_with([bp])
        assert not upgrade_planer.build_steps.called
        assert res['result']['best_phase'] is None

    def test_resolve_upgrade_and_steps_with_goal(self, upgrade_planer: UpgradePlaner, catalog):
        upgrade_planer.build_catalog = mock.Mock(return_value=catalog)
        upgrade_planer.dependency_solver.solve_dependencies = mock.Mock(return_value={
            "results": [{"producer": "1.0.16", "consumer": "1.0.16"}],
            "errors": [],
            "anomalies": []
        })
        bp = Phase([PhasePin(catalog[1], "1.0.16"),
                    PhasePin(catalog[0], "1.0.16")])
        upgrade_planer.solve_best_phase = mock.Mock(return_value=(bp, 1))
        upgrade_planer.build_steps = mock.Mock()

        res = upgrade_planer.resolve_upgrade_and_steps()

        upgrade_planer.solve_best_phase.assert_called_with([bp])
        upgrade_planer.build_steps.assert_called_with(bp)

        assert res['result']['best_phase'] == bp

    def test_resolve_upgrade_and_steps_with_resolution_disabled(self, upgrade_planer: UpgradePlaner, catalog):
        upgrade_planer.config['solve_dependencies'] = False
        upgrade_planer.build_catalog = mock.Mock(return_value=catalog)
        upgrade_planer.dependency_solver.solve_dependencies = mock.Mock(return_value={
            "results": [],
            "errors": [],
            "anomalies": []
        })
        bp = Phase([PhasePin(catalog[1], "1.0.16"),
                    PhasePin(catalog[0], "1.0.16")])
        upgrade_planer.get_latest_phase = mock.Mock(return_value={catalog[1]['name']: "1.0.16",
                                                                  catalog[0]['name']: "1.0.16"})
        upgrade_planer.solve_best_phase = mock.Mock(return_value=(bp, 1))
        upgrade_planer.build_steps = mock.Mock()

        res = upgrade_planer.resolve_upgrade_and_steps()

        upgrade_planer.solve_best_phase.assert_called_with([bp])
        upgrade_planer.build_steps.assert_called_with(bp)
        upgrade_planer.dependency_solver.solve_dependencies.assert_not_called()

        assert res['result']['best_phase'] == bp

    def test_resolve_upgrade_and_steps_with_error(self, upgrade_planer: UpgradePlaner, catalog):
        upgrade_planer.build_catalog = mock.Mock(return_value=catalog)
        upgrade_planer.dependency_solver.solve_dependencies = mock.Mock(return_value={
            "results": [],
            "errors": ["ceci est une erreur"],
            "anomalies": []
        })

        res = upgrade_planer.resolve_upgrade_and_steps()

        print(res)
        assert res == {
            'result': None,
            'errors': {'step': 'dependency_solve', 'error': ['ceci est une erreur'], 'catalog': catalog}
        }


class TestStepComputing(object):

    def test_build_steps(self, upgrade_planer: UpgradePlaner):
        goal = Phase((PhasePin({"name": "producer", }, "1.0.17"), PhasePin({"name": "consumer", }, "1.0.17"),))
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "version": "1.0.16"},
            {"name": "consumer", "version": "1.0.1"}
        ]

        upgrade_planer.explain_phase = mock.Mock(return_value={'results': 0})
        s = upgrade_planer.build_steps(goal)
        assert 2 == len(s)
        assert [('producer', '1.0.16', '1.0.17'), ('consumer', '1.0.1', '1.0.17')] == s

    @pytest.mark.parametrize(
        ('goal_param', 'current_state', 'compatible_phase', 'expected'),
        [
            (  # upgrade two version with only one backward compat

                {'a': "2", "b": "2"},
                {'a': "1", "b": "1"},
                [{'a': "2", "b": "1"}],
                [('a', '1', '2'), ('b', '1', '2')],
            ),
            (  # upgrade two version with only the other backward compat

                {'a': "2", "b": "2"},
                {'a': "1", "b": "1"},
                [{'a': "1", "b": "2"}],
                [('b', '1', '2'), ('a', '1', '2')],
            ),
            (  # goal is already applyed

                {'a': "2", "b": "2"},
                {'a': "2", "b": "2"},
                [],
                [],
            ),
            (  # one service to update

                {'a': "2", "b": "1"},
                {'a': "1", "b": "1"},
                [{'a': "2", "b": "1"}],
                [('a', '1', '2')],
            ),
            (  # 3 services

                {'a': "2", "b": "2", 'c': '2'},
                {"a": "1", "b": "1", "c": "1"},
                [{"a": "1", "b": "1", "c": "2"}, {"a": "1", "b": "2", "c": "2"},
                 {"a": "1", "b": "2", "c": "1"}],
                [('b', '1', '2'), ('c', '1', '2',), ('a', '1', '2')],
            )
        ])
    def test_build_steps_bad_solution(self, goal_param, current_state, compatible_phase, expected, upgrade_planer):
        # mock the phase object to targeted phase.
        goal = Phase([
            PhasePin({"name": k, }, v)
            for k, v in goal_param.items()
        ])
        # mock the content of mongo database with only usefull data: current state
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": k, "version": v}
            for k, v in current_state.items()
        ]

        def explain_phase(phase):
            if phase in compatible_phase or phase == goal_param:
                return {'results': 0}
            else:
                return {'results': 1}

        upgrade_planer.explain_phase = explain_phase
        s = upgrade_planer.build_steps(goal)
        assert expected == s


class TestSolveBestPhase(object):

    def build_catalog(self, service, versions):
        return [{
            "version": v,
            "image_info": {
                'digest': 'sha256:d2a8219e9b3bdc4da656d32c4ac9ad4e54312946a10ac9244967d4373bc3ce6d',
                'image': 'maiev',
                'repository': 'localhost:5000',
                'species': 'producer',
                'tag': '%s-%s' % (service, v),
                'version': v
            },
        }
            for v in versions
        ]

    def test_best_phase(self, upgrade_planer: UpgradePlaner):
        phases = [
            Phase([PhasePin({"name": "producer", }, "1.0.1"), PhasePin({"name": "consumer", }, "1.0.1")]),
            Phase([PhasePin({"name": "producer", }, "1.0.1"), PhasePin({"name": "consumer", }, "1.0.17")]),
            Phase([PhasePin({"name": "producer", }, "1.0.16"), PhasePin({"name": "consumer", }, "1.0.1")]),
            Phase([PhasePin({"name": "producer", }, "1.0.17"), PhasePin({"name": "consumer", }, "1.0.1")]),
            Phase([PhasePin({"name": "producer", }, "1.0.17"), PhasePin({"name": "consumer", }, "1.0.17")]),
        ]
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer", ["1.0.1", "1.0.16", "1.0.17"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.1", "1.0.17"])},
        ]

        s = upgrade_planer.solve_best_phase(phases)
        assert 2 == len(s)
        goal, rank = s
        assert 0 == rank
        assert goal == Phase([PhasePin({"name": "producer", }, "1.0.17"), PhasePin({"name": "consumer", }, "1.0.17")])

    def test_best_phase_beta_version(self, upgrade_planer: UpgradePlaner):
        phases = [
            Phase([PhasePin({"name": "producer", }, "1.0.1b"), PhasePin({"name": "consumer", }, "1.0.1b")]),
            Phase([PhasePin({"name": "producer", }, "1.0.1b"), PhasePin({"name": "consumer", }, "1.0.17b")]),
            Phase([PhasePin({"name": "producer", }, "1.0.16b"), PhasePin({"name": "consumer", }, "1.0.1b")]),
            Phase([PhasePin({"name": "producer", }, "1.0.17b"), PhasePin({"name": "consumer", }, "1.0.1b")]),
            Phase([PhasePin({"name": "producer", }, "1.0.17b"), PhasePin({"name": "consumer", }, "1.0.17b")]),
        ]
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer", ["1.0.1b", "1.0.16b", "1.0.17b"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.1b", "1.0.17b"])},
        ]

        s = upgrade_planer.solve_best_phase(phases)
        assert 2 == len(s)
        goal, rank = s
        assert 0 == rank
        assert goal == Phase([PhasePin({"name": "producer", }, "1.0.17b"),
                              PhasePin({"name": "consumer", }, "1.0.17b")])

    def test_best_phase_rc_version(self, upgrade_planer: UpgradePlaner):
        phases = [
            Phase([PhasePin({"name": "producer", }, "1.0.1rc1"), PhasePin({"name": "consumer", }, "1.0.1rc1")]),
            Phase([PhasePin({"name": "producer", }, "1.0.1rc1"), PhasePin({"name": "consumer", }, "1.0.1rc17")]),
            Phase([PhasePin({"name": "producer", }, "1.0.1rc16"), PhasePin({"name": "consumer", }, "1.0.1rc1")]),
            Phase([PhasePin({"name": "producer", }, "1.0.1rc17"), PhasePin({"name": "consumer", }, "1.0.1rc1")]),
            Phase([PhasePin({"name": "producer", }, "1.0.1rc17"), PhasePin({"name": "consumer", }, "1.0.1rc17")]),
        ]
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer",
                                                                     ["1.0.1rc1", "1.0.1rc16", "1.0.1rc17"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.1rc1", "1.0.1rc17"])},
        ]

        s = upgrade_planer.solve_best_phase(phases)
        assert 2 == len(s)
        goal, rank = s
        assert 0 == rank
        assert goal == Phase([PhasePin({"name": "producer", }, "1.0.1rc17"),
                              PhasePin({"name": "consumer", }, "1.0.1rc17")])

    def test_best_phase2(self, upgrade_planer: UpgradePlaner):
        phases = [
            [[{"name": "producer", }, "1.0.1"], [{"name": "consumer", }, "1.0.1"]],
            [[{"name": "producer", }, "1.0.1"], [{"name": "consumer", }, "1.0.17"]],
            [[{"name": "producer", }, "1.0.16"], [{"name": "consumer", }, "1.0.1"]],
            [[{"name": "producer", }, "1.0.17"], [{"name": "consumer", }, "1.0.1"]],
        ]
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer", ["1.0.1", "1.0.16", "1.0.17"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.1", "1.0.17"])},
        ]

        s = upgrade_planer.solve_best_phase(phases)
        assert 2 == len(s)
        goal, rank = s
        assert 1 == rank
        assert goal == [[{"name": "producer", }, "1.0.17"], [{"name": "consumer", }, "1.0.1"]]

    def test_best_phase3(self, upgrade_planer: UpgradePlaner):
        phases = [
            [[{"name": "producer", }, "1.0.1"], [{"name": "consumer", }, "1.0.1"]],
            [[{"name": "producer", }, "1.0.1"], [{"name": "consumer", }, "1.0.17"]],
            [[{"name": "producer", }, "1.0.16"], [{"name": "consumer", }, "1.0.1"]],
        ]
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer", ["1.0.1", "1.0.16", "1.0.17"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.1", "1.0.17"])},
        ]

        s = upgrade_planer.solve_best_phase(phases)
        assert 2 == len(s)
        goal, rank = s
        assert 2 == rank
        assert goal == [[{"name": "producer", }, "1.0.1"], [{"name": "consumer", }, "1.0.17"]]

    def test_get_latest_phase(self, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer", ["1.0.5", "1.0.16", "1.0.17"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.5", "1.0.17"])},
        ]

        s = upgrade_planer.get_latest_phase()
        assert {"producer": "1.0.17", "consumer": "1.0.17"} == s

    def test_get_latest_phase_beta(self, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog("producer", ["1.0.5", "1.0.16b", "1.0.17"])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.5", "1.0.17b"])},
        ]

        s = upgrade_planer.get_latest_phase()
        assert {"producer": "1.0.17", "consumer": "1.0.17b"} == s

    def test_get_latest_phase_beta_real(self, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find.return_value = [
            {"name": "producer", "versions_list": self.build_catalog(
                "producer", ['1.1-93b', '1.1-79b', '1.1-73b', '1.1-77b', '1.1-78b', '1.1-71b', '1.1-87b', '1.1-64b',
                             '1.1-89b', '1.1-84b', '1.1-86b', '1.1-65b', '1.1-88b', '1.1-96b', '1.1-97b', '1.1-98b',
                             '1.1-99b', '1.1-100b', '1.1-101b', '1.1-103b', '1.1-104b', '1.1-106b', '1.1-107b',
                             '1.1-108b', '1.3.0-110b', '1.3.0-114b', '1.3.0-119b'])},
            {"name": "consumer", "versions_list": self.build_catalog("consumer", ["1.0.5", "1.0-17b"])},
        ]

        s = upgrade_planer.get_latest_phase()
        assert {"producer": "1.3.0-119b", "consumer": "1.0.5"} == s

    def test_sort_version(self, upgrade_planer: UpgradePlaner):
        versions = ['1.1.4-108b', '1.3.0-110b', '1.3.0-114b', '1.3.0-119b']
        sorted_v = upgrade_planer.sort_versions(self.build_catalog("producer", versions))
        assert sorted_v == ['1.3.0-119b', '1.3.0-114b', '1.3.0-110b', '1.1.4-108b']

    def test_sort_mixed_version(self, upgrade_planer: UpgradePlaner):
        versions = ['1.1.4.108b', '1.3.0.110b', '1.3.0.114b', '1.3.0.119b', '1.3.1-120b', '1.3.1-125b']
        sorted_v = upgrade_planer.sort_versions(self.build_catalog("producer", versions))

        assert sorted_v == ['1.3.1-125b', '1.3.1-120b', '1.3.0.110b', '1.3.0.114b', '1.3.0.119b', '1.1.4.108b']


class TestPerfRealData(object):

    def load_sample(self, sample):
        with open(os.path.join(os.path.dirname(__file__), 'samples', sample)) as f:
            return json.load(f)

    def test_sample1_get_latest(self, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find.return_value = self.load_sample('sample1.json')['catalog']
        s = upgrade_planer.get_latest_phase()
        assert s == {
            'http_to_rpc': '0.1.24',
            'joboffer_algolia_publisher': '0.1.24',
            'joboffer_fetcher': '0.1.24',
            'joboffer_xml_publisher': '0.1.24',
            'maiev': '1.3.0',
            'yupeeposting-backend': '0.2.65',
            'yupeeposting-webui': '0.2.64'}

    def test_sample1_build_catalog(self, upgrade_planer: UpgradePlaner):
        upgrade_planer.mongo.catalog.find.return_value = self.load_sample('sample1.json')['catalog']
        catalog = upgrade_planer.build_catalog()

        total = reduce(lambda a, b: a * b, (len(service['versions']) for service in catalog), 1)
        assert total == 8640
        reduced = upgrade_planer.reduce_catalog(catalog)
        total_reduced = reduce(lambda a, b: a * b, (len(service['versions']) for service in reduced), 1)
        assert total_reduced == 32
