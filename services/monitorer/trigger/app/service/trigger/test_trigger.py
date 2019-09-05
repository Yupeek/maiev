# -*- coding: utf-8 -*-
import copy
import datetime
import logging
import os
import random
import sys
from unittest import TestCase

import mock
from nameko.testing.services import worker_factory
from pymongo import MongoClient

from common.db.mongo import Mongo
from service.trigger.trigger import Trigger, get_now

logger = logging.getLogger(__name__)

FIXTURES_RULESETS = [
    {
        'owner': 'overseer',
        'name': 'stable_producer',
        'resources': [
            {
                'name': 'rmq',
                'monitorer': 'monitorer_rabbitmq',
                'identifier': 'rpc-producer',
            }
        ],
        'rules': [
            {
                'name': 'latency_ok',
                'expression': 'rmq:latency < 0.200'
            },
            {
                'name': 'latency_fail',
                'expression': 'rmq:latency > 5'
            },
            {
                'name': 'panic',
                'expression': 'rmq:latency > 10 or (rules:latency_fail and rules:latency_fail:since > "25s")'
            },
            {
                'name': 'stable_latency',
                'expression': 'rules:latency_ok and rules:latency_ok:since > "30s"'
            }
        ]
    }, {
        'owner': 'overseer',
        'name': 'naiv_producer',
        'resources': [
            {
                'name': 'rmq',
                'monitorer': 'monitorer_rabbitmq',
                'identifier': 'rpc-producer',
            }
        ],
        'rules': [
            {
                'name': 'latency_ok',
                'expression': 'rmq:latency < 0.200'
            },
            {
                'name': 'latency_fail',
                'expression': 'rmq:latency > 5'
            }
        ]
    }, {
        'owner': 'overseer_gui',
        'name': 'swap_rate',
        'resources': [
            {
                'name': 'rmq',
                'monitorer': 'monitorer_rabbitmq',
                'identifier': 'rpc-producer',
            }
        ],
        'rules': [
            {
                'name': 'rate_up',
                'expression': 'rmq:rate < 0'
            },
            {
                'name': 'rate_down',
                'expression': 'rmq:rate > 0'
            }
        ]
    }
]


class TriggerTestcase(TestCase):
    fixtures_rulesets = FIXTURES_RULESETS

    def setUp(self):
        self.service = worker_factory(Trigger)  # type: Trigger

    def add_history(self, ruleset, resources=None, rules=None, get_now=get_now):
        ruleset = copy.deepcopy(ruleset)
        resources = resources or {}
        rules = rules or {}

        for resource_name, val_or_t in resources.items():
            if isinstance(val_or_t, (list, tuple)):
                val, since = val_or_t
            else:
                val, since = val_or_t, 0
            for resource in ruleset['resources']:
                if resource['name'] == resource_name:
                    resource['history'] = {
                        'date': get_now() - datetime.timedelta(seconds=since),
                        'last_metrics': val
                    }
        for rule_name, val_or_t in rules.items():
            if isinstance(val_or_t, (list, tuple)):
                val, since = val_or_t
            else:
                val, since = val_or_t, 0
            for rule in ruleset['rules']:
                if rule['name'] == rule_name:
                    rule['history'] = {
                        'date': get_now() - datetime.timedelta(seconds=since),
                        'last_result': val
                    }
        return ruleset


class TestNoTrigger(TestCase):
    def setUp(self):
        self.service = worker_factory(Trigger)  # type: Trigger

    def parse(self, rules, metrics=None, others=()):
        rule_str = rules
        rules = []
        for other_name, other_stmt in others:
            rules.append({
                'name': other_name,
                'expression': other_stmt,
                'history': {
                    'date': get_now() - datetime.timedelta(seconds=16)
                }
            })
        rules.append({
            'name': '__main__',
            'expression': rule_str
        })
        ruleset = {
            'owner': 'me',
            'name': '__main__',
            'resources': [
                {
                    'name': 'rmq',
                    'monitorer': 'monitorer_rabbitmq',
                    'identifier': 'rpc-producer',
                    'history': {
                        "last_metrics": metrics or {},
                        "date": get_now()
                    }
                }
            ],
            'rules': rules
        }
        return self.service._compute_ruleset(ruleset)['__main__']

    def assert_rule_true(self, *args):
        self.assertTrue(self.parse(*args))

    def assert_rule_false(self, *args):
        self.assertFalse(self.parse(*args))

    def test_solve_simple(self):
        self.assert_rule_true('rmq:latency < 5', {'latency': 4})
        self.assert_rule_true('rmq:latency <= 5', {'latency': 5})
        self.assert_rule_false('rmq:latency < 5', {'latency': 5})
        self.assert_rule_false('rmq:latency < 5', {'latency': 6})

    def test_solve_recursive(self):
        self.assert_rule_true('rules:functional', {'latency': 4}, [('functional', '1 == 1')])
        self.assert_rule_true('rmq:latency < 5 and rules:functional', {'latency': 4}, [('functional', '1 == 1')])
        self.assert_rule_false('rmq:latency < 5 and not rules:functional', {'latency': 6}, [('functional', '1 == 1')])
        self.assert_rule_false('rmq:latency < 5 and rules:functional', {'latency': 4}, [('functional', '1 == 0')])
        self.assert_rule_false('rmq:latency < 5 and not rules:functional', {'latency': 6}, [('functional', '1 == 0')])


class TestResolveRulesetsHistory(TriggerTestcase):
    def test_no_history(self):
        ruleset = self.add_history(self.fixtures_rulesets[0])

        res = self.service._compute_ruleset(ruleset)
        self.assertIsNone(res)

    def test_with_metric_history_latency_fail(self):
        ruleset = self.add_history(
            self.fixtures_rulesets[0],
            resources={
                'rmq': ({'latency': 6.8}, 68)
            }
        )
        res = self.service._compute_ruleset(ruleset)
        self.assertEqual(res, {'latency_ok': False, 'panic': False, 'stable_latency': False, 'latency_fail': True})

    def test_with_metric_history_latency_ok(self):
        ruleset = self.add_history(
            self.fixtures_rulesets[0],
            resources={
                'rmq': ({'latency': 0.1}, 68)
            }
        )
        res = self.service._compute_ruleset(ruleset)
        self.assertEqual(res, {'latency_ok': True, 'panic': False, 'stable_latency': False, 'latency_fail': False})

    def test_with_metric_history_panic1(self):
        ruleset = self.add_history(
            self.fixtures_rulesets[0],
            resources={
                'rmq': ({'latency': 11}, 68)
            }
        )
        res = self.service._compute_ruleset(ruleset)
        self.assertEqual(res, {'latency_ok': False, 'panic': True, 'stable_latency': False, 'latency_fail': True})

    def test_with_metric_history_no_panic(self):
        ruleset = self.add_history(
            self.fixtures_rulesets[0],
            resources={
                'rmq': ({'latency': 6}, 68)
            },
            rules={
                'latency_fail': [True, 23]  # fail since 23 sec
            }
        )
        res = self.service._compute_ruleset(ruleset)
        self.assertEqual(res, {'latency_ok': False, 'panic': False, 'stable_latency': False, 'latency_fail': True})

    def test_with_metric_history_panic_latency_since(self):
        ruleset = self.add_history(
            self.fixtures_rulesets[0],
            resources={
                'rmq': ({'latency': 6}, 68)
            },
            rules={
                'latency_fail': [True, 27]  # fail since 23 sec
            }
        )
        res = self.service._compute_ruleset(ruleset)
        self.assertEqual(res, {'latency_ok': False, 'panic': True, 'stable_latency': False, 'latency_fail': True})

    def test_with_metric_history_stable_latency(self):
        ruleset = self.add_history(
            self.fixtures_rulesets[0],
            resources={
                'rmq': ({'latency': 0.05}, 68)
            },
            rules={
                'latency_ok': [True, 33]  # fail since 23 sec
            }
        )
        res = self.service._compute_ruleset(ruleset)
        self.assertEqual(res, {'latency_ok': True, 'panic': False, 'stable_latency': True, 'latency_fail': False})


class TestConputeResults(TriggerTestcase):
    def test_bad_ruleset(self):
        self.assertEqual(self.service.compute({}), {
            "status": "error",
            "exception": "missing key for ruleset : 'owner'",
            "exception_type": "KeyError",
            "result": None,
            "exception_extra": {}
        })

        self.assertEqual(self.service.compute({
            'owner': 'overseer_gui',
            'name': 'swap_rate',
        }), {
            "status": "error",
            "exception": "can't add ruleset without bound resources to monitor",
            "exception_type": "ValueError",
            "result": None,
            "exception_extra": {}
        })

    def test_incomplete_ruleset(self):
        ruleset = {
            'owner': 'overseer_gui',
            'name': 'swap_rate',
            'resources': [
                {
                    'name': 'rmq',

                    'identifier': 'rpc-producer',
                }
            ],
            'rules': [
                {
                    'name': 'rate_up',

                },
                {
                    'name': 'rate_down',
                    'expression': 'rmq:rate > 0'
                }
            ]
        }
        self.assertEqual(self.service.compute(ruleset), {
            "status": "error",
            "exception": "missing key for ruleset : 'monitorer'",
            "exception_type": "KeyError",
            "result": None,
            "exception_extra": {}
        })

    def test_empty_rules(self):
        ruleset = {
            'owner': 'overseer_gui',
            'name': 'swap_rate',
            'resources': [
                {
                    'name': 'rmq',
                    'monitorer': 'monitorer_rabbitmq',
                    'identifier': 'rpc-producer',
                }
            ],
            'rules': [
            ]
        }
        ruleset = self.add_history(ruleset, resources={'rmq': [{'rate': 1}, 0]})

        self.assertEqual(self.service.compute(ruleset), {
            "status": "success",
            "result": {},
        })

    def test_bad_syntax_ruleset(self):
        ruleset = {
            'owner': 'overseer_gui',
            'name': 'swap_rate',
            'resources': [
                {
                    'name': 'rmq',
                    'monitorer': 'monitorer_rabbitmq',
                    'identifier': 'rpc-producer',
                }
            ],
            'rules': [
                {
                    'name': 'rate_up',
                    'expression': 'rmq:rate < 0 & lol and rate < 0'
                }
            ]
        }
        ruleset = self.add_history(ruleset, resources={'rmq': [{'rate': 1}, 0]})
        expected = {
            "status": "error",
            "exception": 'Expected end of text (at char 13), (line:1, col:14)',
            "exception_type": "ParseException",
            "result": None,
            "exception_extra": {
                "loc": 13,
                "pstr": 'rmq:rate < 0 & lol and rate < 0'
            }
        }
        if sys.version_info > (3, 6, 6):
            expected['exception'] = "Expected end of text, found '&'  (at char 13), (line:1, col:14)"
        self.assertEqual(self.service.compute(ruleset), expected)

    def test_scope_error(self):
        ruleset = {
            'owner': 'overseer_gui',
            'name': 'swap_rate',
            'resources': [
                {
                    'name': 'rmq',
                    'monitorer': 'monitorer_rabbitmq',
                    'identifier': 'rpc-producer',
                }
            ],
            'rules': [
                {
                    'name': 'rate_up',
                    'expression': 'rmq:rate < 0 and lol and rate < 0'
                }
            ]
        }
        ruleset = self.add_history(ruleset, resources={'rmq': [{'rate': 1}, 0]})
        self.assertEqual(self.service.compute(ruleset), {
            "status": "error",
            "exception": 'No such object "lol"',
            "exception_type": "ScopeError",
            "result": None,
            "exception_extra": {}
        })

    def test_good_ruleset(self):
        ruleset = self.fixtures_rulesets[2]

        self.assertEqual(self.service.compute(
            self.add_history(ruleset, resources={'rmq': [{'rate': 1}, 0]})
        ), {
            "status": "success",
            "result": {
                'rate_up': False,
                'rate_down': True
            },
        })
        self.assertEqual(self.service.compute(
            self.add_history(ruleset, resources={'rmq': [{'rate': -1}, 0]})
        ), {
            "status": "success",
            "result": {
                'rate_up': True,
                'rate_down': False
            },
        })
        self.assertEqual(self.service.compute(
            self.add_history(ruleset, resources={'rmq': [{'rate': 0}, 0]})
        ), {
            "status": "success",
            "result": {
                'rate_up': False,
                'rate_down': False
            },
        })

    def test_number_None(self):
        ruleset = self.fixtures_rulesets[0]

        self.assertEqual(self.service.compute(
            self.add_history(ruleset, resources={'rmq': [{'latency': None}, 0]})
        ), {
            "status": "success",
            "result": {'latency_ok': False, 'panic': False, 'stable_latency': False, 'latency_fail': False},
        })

    def test_no_ressources_ruleset(self):
        ruleset = {
            'owner': 'overseer_gui',
            'name': 'swap_rate',
            'resources': [
            ],
            'rules': [
                {
                    'name': 'rate_up',
                    'expression': 'rmq:rate < 0'
                },
                {
                    'name': 'rate_down',
                    'expression': 'rmq:rate > 0'
                }
            ]
        }
        self.assertEqual(self.service.compute(ruleset), {
            "status": "error",
            "exception": "can't add ruleset without bound resources to monitor",
            "exception_type": "ValueError",
            "result": None,
            "exception_extra": {}
        })


class WithDbTestTrigger(TriggerTestcase):
    dbname = "test_maiev_%d" % random.randint(0, 65535)

    @classmethod
    def setUpClass(cls):
        cls.mongo_cnx = MongoClient(os.environ.get('MONGO_TEST_URI', "localhost"))
        cls.db = cls.mongo_cnx[cls.dbname]
        super(WithDbTestTrigger, cls).setUpClass()

    def tearDown(self):
        super(WithDbTestTrigger, self).setUp()
        self.mongo_cnx.drop_database(self.dbname)

    def setUp(self):
        super(WithDbTestTrigger, self).setUp()
        self.service = worker_factory(Trigger, mongo=self.db)  # type: Trigger
        self.rulesets = self.service.mongo.rulesets


class TestStorageMethods(WithDbTestTrigger):
    def test_add(self):
        self.assertEqual(self.rulesets.count(), 0)

        self.service.add(self.fixtures_rulesets[0])
        self.assertEqual(self.rulesets.count(), 1)
        self.service.add(self.fixtures_rulesets[1])
        self.assertEqual(self.rulesets.count(), 2)
        self.service.add(self.fixtures_rulesets[1])
        self.assertEqual(self.rulesets.count(), 2)

    def test_add_replacement(self):
        self.assertEqual(self.rulesets.count(), 0)

        self.service.add(self.fixtures_rulesets[1])
        self.assertEqual(self.rulesets.count(), 1)
        stored = self.rulesets.find_one({'owner': 'overseer', 'name': 'naiv_producer'})
        self.assertEqual(len(stored['resources']), 1)
        ruleset = {
            'owner': 'overseer',
            'name': 'naiv_producer',
            'resources': [
            ],
            'rules': []
        }
        # this will replace previous added ruleset
        self.service.add(ruleset)
        stored = self.rulesets.find_one({'owner': 'overseer', 'name': 'naiv_producer'})
        self.assertEqual(len(stored['resources']), 0)

    def test_delete(self):
        self.service.add(self.fixtures_rulesets[0])
        self.service.add(self.fixtures_rulesets[1])
        self.service.add(self.fixtures_rulesets[2])
        # removeing
        self.assertIsNotNone(self.rulesets.find_one({'owner': 'overseer', 'name': 'naiv_producer'}))
        self.service.delete('overseer', 'naiv_producer')
        self.assertIsNone(self.rulesets.find_one({'owner': 'overseer', 'name': 'naiv_producer'}))
        self.assertEqual(self.rulesets.count(), 2)
        # already removed
        self.service.delete('overseer', 'naiv_producer')
        self.assertIsNone(self.rulesets.find_one({'owner': 'overseer', 'name': 'naiv_producer'}))
        self.assertEqual(self.rulesets.count(), 2)
        # removing another
        self.assertIsNotNone(self.rulesets.find_one({'owner': 'overseer_gui', 'name': 'swap_rate'}))
        self.service.delete('overseer_gui', 'swap_rate')
        self.assertIsNone(self.rulesets.find_one({'owner': 'overseer_gui', 'name': 'swap_rate'}))
        self.assertEqual(self.rulesets.count(), 1)

    def test_purge(self):
        self.service.add(self.fixtures_rulesets[0])
        self.service.add(self.fixtures_rulesets[1])
        self.service.add(self.fixtures_rulesets[2])
        self.assertEqual(self.rulesets.find({'owner': 'overseer'}).count(), 2)
        self.assertEqual(self.rulesets.find({'owner': 'overseer_gui'}).count(), 1)
        # purge
        self.service.purge('overseer')
        self.assertEqual(self.rulesets.find({'owner': 'overseer'}).count(), 0)
        self.assertEqual(self.rulesets.find({'owner': 'overseer_gui'}).count(), 1)
        # purge no effect
        self.service.purge('overseer')
        self.assertEqual(self.rulesets.find({'owner': 'overseer'}).count(), 0)
        self.assertEqual(self.rulesets.find({'owner': 'overseer_gui'}).count(), 1)
        # purge no effect
        self.service.purge('overseer_gui')
        self.assertEqual(self.rulesets.find({'owner': 'overseer'}).count(), 0)
        self.assertEqual(self.rulesets.find({'owner': 'overseer_gui'}).count(), 0)

    def test_list(self):
        self.service.add(self.fixtures_rulesets[0])
        self.service.add(self.fixtures_rulesets[1])
        self.service.add(self.fixtures_rulesets[2])

        self.assertEqual(len(self.service.list()), 3)
        self.assertEqual(len(self.service.list(owner='overseer_gui')), 1)
        self.assertEqual(len(self.service.list(owner='overseer')), 2)
        self.assertEqual(len(self.service.list(owner='overseer', )), 2)
        self.assertEqual(len(self.service.list(owner='overseer2', )), 0)
        self.assertEqual(len(self.service.list(owner='overseer', name='naiv_producer')), 1)


class TestEventComputing(WithDbTestTrigger):
    events = [
        {
            "monitorer": "monitorer_rabbitmq",
            "identifier": "rpc-producer",
            "metrics": {
                'waiting': 2238,
                'latency': 25.902,
                'rate': 86.4,
                'call_rate': 0.0,
                'exec_rate': 86.4,
                'consumers': 1,
            }
        }
    ]

    def test_trigger_unknown_event(self):
        _compute_ruleset = self.service._compute_ruleset
        with mock.patch.object(self.service, '_compute_ruleset') as compute_ruleset:
            compute_ruleset.side_effect = _compute_ruleset
            self.service.on_metrics_updated(self.events[0])
            self.service.dispatch.assert_not_called()
            compute_ruleset._compute_ruleset.assert_not_called()

    def test_trigger_known_event(self):
        self.service.add(self.fixtures_rulesets[0])
        _compute_ruleset = self.service._compute_ruleset
        now = datetime.datetime.now()
        with mock.patch('service.trigger.trigger.get_now', side_effect=lambda: now):
            with mock.patch.object(self.service, '_compute_ruleset') as compute_ruleset:
                compute_ruleset.side_effect = _compute_ruleset
                self.service.on_metrics_updated(self.events[0])
                self.service.dispatch.assert_called_once_with('ruleset_triggered', {
                    'ruleset': self.add_history(self.fixtures_rulesets[0],
                                                resources={'rmq': self.events[0]['metrics']},
                                                rules={'panic': True, 'latency_fail': True,
                                                       'stable_latency': False, 'latency_ok': False},
                                                get_now=lambda: now
                                                ),
                    'rules_stats': {'panic': True, 'latency_fail': True, 'stable_latency': False, 'latency_ok': False},
                })
                compute_ruleset.assert_called_once()


class TestSpecificSetup(WithDbTestTrigger):

    def test_store_history_one(self):
        self.rulesets.insert_one({
            "owner": "overseer_load_manager",
            "name": "gmd_joboffer_xml_publisher",
            "resources": [
                {
                    "name": "rmq",
                    "monitorer": "monitorer_rabbitmq",
                    "identifier": "rpc-ECMC_joboffer_xml_publisher",
                    "history": {}
                }
            ],
            "rules": [
                {
                    "name": "__scale_down__",
                    "expression": "rules:stable_latency and rmq:consumers > 0",
                    "history": None
                }
            ]
        })

        assert self.rulesets.find_one()["resources"][0]['history'] == {}
        self.service.on_metrics_updated({
            "monitorer": "monitorer_rabbitmq", "identifier": "rpc-ECMC_joboffer_xml_publisher",
            "metrics":
                {"exists": True, "waiting": 0, "latency": None, "rate": None,
                 "call_rate": 0, "exec_rate": 0, "consumers": 3
                 }})

        history = self.rulesets.find_one()["resources"][0]['history']
        assert history != {}
        assert history['last_metrics'] == {
            'exists': True, 'waiting': 0, 'latency': None, 'rate': None,
            'call_rate': 0, 'exec_rate': 0, 'consumers': 3
        }

    def test_store_history_multi_same_history(self):
        self.rulesets.insert_one({
            "owner": "overseer_load_manager",
            "name": "gmd_joboffer_xml_publisher",
            "resources": [
                {
                    "name": "rmq",
                    "monitorer": "monitorer_rabbitmq",
                    "identifier": "rpc-ECMC_joboffer_xml_publisher",
                    "history": {}
                },
                {
                    "name": "rmq2",
                    "monitorer": "monitorer_rabbitmq",
                    "identifier": "rpc-ECMC_joboffer_xml_publisher",
                    "history": {}
                }
            ],
            "rules": [
                {
                    "name": "__scale_down__",
                    "expression": "rules:stable_latency and rmq:consumers > 0",
                    "history": None
                }
            ]
        })

        assert self.rulesets.find_one()["resources"][0]['history'] == {}
        assert self.rulesets.find_one()["resources"][1]['history'] == {}
        self.service.on_metrics_updated(
            {"monitorer": "monitorer_rabbitmq", "identifier": "rpc-ECMC_joboffer_xml_publisher",
             "metrics": {"exists": True, "waiting": 0, "latency": None, "rate": None, "call_rate": 0, "exec_rate": 0,
                         "consumers": 3}})
        history = self.rulesets.find_one()["resources"][0]['history']
        history2 = self.rulesets.find_one()["resources"][1]['history']
        assert history != {}
        assert history['last_metrics'] == {
            'exists': True, 'waiting': 0, 'latency': None, 'rate': None,
            'call_rate': 0, 'exec_rate': 0, 'consumers': 3
        }
        assert history2 != {}
        assert history2['last_metrics'] == {
            'exists': True, 'waiting': 0, 'latency': None, 'rate': None,
            'call_rate': 0, 'exec_rate': 0, 'consumers': 3
        }

    def test_store_history_multi_different_resources(self):
        self.rulesets.insert_one({
            "owner": "overseer_load_manager",
            "name": "gmd_joboffer_xml_publisher",
            "resources": [
                {
                    "name": "rmq",
                    "monitorer": "monitorer_rabbitmq",
                    "identifier": "rpc-ECMC_joboffer_xml_publisher",
                    "history": {}
                },
                {
                    "name": "rmq2",
                    "monitorer": "monitorer_rabbitmq",
                    "identifier": "rpc-ECMC_joboffer_algolia_publisher",
                    "history": {}
                }
            ],
            "rules": [
                {
                    "name": "__scale_down__",
                    "expression": "rules:stable_latency and rmq:consumers > 0",
                    "history": None
                }
            ]
        })

        assert self.rulesets.find_one()["resources"][0]['history'] == {}
        assert self.rulesets.find_one()["resources"][1]['history'] == {}
        self.service.on_metrics_updated(
            {"monitorer": "monitorer_rabbitmq", "identifier": "rpc-ECMC_joboffer_xml_publisher",
             "metrics": {"exists": True, "waiting": 0, "latency": None, "rate": None, "call_rate": 0, "exec_rate": 0,
                         "consumers": 3}})
        history = self.rulesets.find_one()["resources"][0]['history']
        history2 = self.rulesets.find_one()["resources"][1]['history']
        assert history != {}
        assert history['last_metrics'] == {
            'exists': True, 'waiting': 0, 'latency': None, 'rate': None,
            'call_rate': 0, 'exec_rate': 0, 'consumers': 3
        }
        assert history2 == {}
