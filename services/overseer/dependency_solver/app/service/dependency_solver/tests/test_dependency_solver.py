# -*- coding: utf-8 -*-
import copy
import json
import logging
import os
import time

import pytest

from service.dependency_solver.dependency_solver import DependencySolver, Solver

logger = logging.getLogger(__name__)


@pytest.fixture
def dependency_solver():
    service = DependencySolver()
    return service


class TestSolver:
    CATALOG1 = [
        {
            "name": "service1",
            "versions": {
                1: {
                    "provide": {
                        "service1:version": 1,
                        "service1:event:ping": 1, "service1:rpc:hello": 1, "service1:rpc:hello:args": ["name"]
                    },
                    "require": []
                },
                2: {
                    "provide": {
                        "service1:version": 2,
                        "service1:event:ping": 1, "service1:rpc:hello": 2, "service1:rpc:hello:args": ["name", "world"]
                    },
                    "require": []
                }
            }
        },
        {
            "name": "service2",
            "versions": {
                1: {
                    "provide": {"service2:event:ping": 1, "service2:rpc:hello": 1, "service2:rpc:print:args": ["val"]},
                    "require": ["service1:event:ping", "service1:rpc:hello == 1"]
                },
                2: {
                    "provide": {"service2:event:ping": 1, "service2:rpc:hello": 1, "service2:rpc:print:args": ["val"]},
                    "require": ["service1:event:ping", "service1:rpc:hello == 2", '"world" in service1:rpc:hello:args']
                },
            }
        }
    ]

    CATALOG_INSOLVABLE = [
        {
            "name": "db",
            "versions": {
                1: {
                    "provide": {
                        "db:table:user": 1,
                        "db:table:user:cols": ['username', 'passwd'],
                    },
                    "require": []
                },
            }
        },
        {
            "name": "auth",
            "versions": {
                1: {
                    "provide": {
                        "auth:rpc:login": 1,
                    },
                    "require": ["db:table:user == 1"]
                },
                2: {
                    "provide": {
                        "auth:rpc:login": 2,
                    },
                    "require": ['"lastlogin" in db:table:user:cols']
                },
            }
        }
    ]

    def test_build_symbol(self):
        s = Solver(self.CATALOG1, ())
        t = s.compile_symbole_table()
        objects_ = {st.global_name: st for st in t.subtables}

        assert t.global_name == 'root'
        assert set(o.global_name for o in t.objects) == {"service1", "service2"}
        assert set(objects_) == {"service1", "service2"}

        s1_ = {st.global_name: st for st in objects_['service1'].subtables}
        assert set(o.global_name for o in objects_['service1'].objects) == {'event', 'rpc', 'version'}
        assert set(s1_) == {'event', 'rpc'}

        s2_ = {st.global_name: st for st in s1_['rpc'].subtables}
        assert set(o.global_name for o in s1_['rpc'].objects) == {'hello'}
        assert set(s2_) == {'hello'}

        s3_ = {st.global_name: st for st in s2_['hello'].subtables}
        assert set(o.global_name for o in s2_['hello'].objects) == {'args'}
        assert set(s3_) == set()

    def test_build_conditions(self):
        s = Solver(self.CATALOG1, ())
        st = s.compile_symbole_table()
        t = s.compile_conditions(st)

        assert set(t) == {'service1', 'service2'}
        assert set(t['service1']) == {1, 2}
        assert set(t['service2']) == {1, 2}

        assert set(t['service1'][1]) == set()
        assert set(t['service1'][2]) == set()

        assert len(t['service2'][1]) == 2
        assert len(t['service2'][2]) == 3

    def test_solve(self):
        s = Solver(self.CATALOG1, ())
        expected_solutions = [
            (('service1', 2), ('service2', 2)),
            (('service1', 1), ('service2', 1)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            assert dict(expected) == solution

    def test_solve_extra1(self):
        s = Solver(self.CATALOG1, ("service1 == 2",))
        expected_solutions = [
            (('service1', 2), ('service2', 2)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            assert dict(expected) == solution

    def test_solve_extra2(self):
        s = Solver(self.CATALOG1, ("service1:version == 1",))
        expected_solutions = [
            (('service1', 1), ('service2', 1)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            assert dict(expected) == solution

    def test_solve_not_possible(self):
        s = Solver(self.CATALOG1, ("not service1",))
        assert 0 == len(list(s.solve()))

    def test_insolvable(self):
        s = Solver(self.CATALOG_INSOLVABLE, ())
        expected_solutions = [
            (('db', 1), ('auth', 1)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            assert dict(expected) == solution

    def test_added_solution_insolvable(self):
        c = copy.deepcopy(self.CATALOG_INSOLVABLE)
        c[0]['versions'][2] = {
            "provide": {
                "db:table:user": 2,
                "db:table:user:cols": ['username', 'passwd', 'lastlogin'],
            },
            "require": []
        }
        s = Solver(c, ())
        expected_solutions = [
            (('db', 2), ('auth', 2)),
            (('db', 1), ('auth', 1)),
            (('db', 2), ('auth', 1)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            assert dict(expected) == solution

    def test_complex_self_dependent(self):
        catalog = [{'name': 'maiev',
                    'versions': {
                        '1.1.52b': {
                            'provide': {
                                'dependency_solver:rpc:solve_dependencies': 1,
                                'dependency_solver:rpc:solve_dependencies:args': ['catalog',
                                                                                  'extra_constraints'],
                                'dependency_solver:rpc:solve_dependencies:rtype': ['list'],
                                'dependency_solver:rpc:explain': 1,
                                'dependency_solver:rpc:explain:args': ['catalog',
                                                                       'extra_constraints'],
                                'dependency_solver:rpc:explain:rtype': ['results'],
                                'upgrade_planer:event:new_version': 1,
                                'upgrade_planer:rpc:list_catalog': 1,
                                'upgrade_planer:rpc:explain_phase': 1,
                                'upgrade_planer:rpc:get_latest_phase': 1,
                                'upgrade_planer:rpc:run_available_upgrade': 1,
                                'upgrade_planer:rpc:continue_scheduled_plan': 1,
                                'upgrade_planer:rpc:resolve_upgrade_and_steps': 1,
                                'overseer:rpc': 1,
                                'overseer:rpc:scale': 1,
                                'overseer:rpc:monitor': 1,
                                'overseer:rpc:list_service': 1,
                                'overseer:rpc:get_service': 1,
                                'overseer:rpc:unmonitor_service': 1,
                                'overseer:rpc:test': 1,
                                'overseer:rpc:upgrade_service': 1,
                                'overseer:event:service_updated': 1,
                                'overseer:event:new_image': 1,
                                'load_manager:rpc:monitor_service': 1,
                                'load_manager:rpc:unmonitor_service': 1,
                                'load_manager:event:scale': 1,
                                'load_manager:event:scale:params': ['scale',
                                                                    'extra_constraints'],
                                'scaler_docker:http': 1,
                                'scaler_docker:event:service_updated': 1,
                                'scaler_docker:event:image_updated': 1,
                                'scaler_docker:rpc:update': 1,
                                'scaler_docker:rpc:get': 1,
                                'scaler_docker:rpc:list_services': 1,
                                'scaler_docker:rpc:fetch_image_config': 1,
                                'monitorer:rabbitmq': True,
                                'monitorer_rabbitmq:event:metrics_updated': 2,
                                'monitorer_rabbitmq:event:metrics_updated:params': [
                                    'monitorer',
                                    'identifier',
                                    'metrics',
                                    'metrics.exists',
                                    'metrics.waiting',
                                    'metrics.latency',
                                    'metrics.rate',
                                    'metrics.call_rate',
                                    'metrics.exec_rate',
                                    'metrics.consumers'],
                                'monitorer_rabbitmq:rpc:track': 1,
                                'monitorer_rabbitmq:rpc:track:args': ['queue_identifier'],
                                'trigger:rpc:compute': 1,
                                'trigger:rpc:compute:args': ['ruleset'],
                                'trigger:rpc:add': 1,
                                'trigger:rpc:add:args': ['ruleset'],
                                'trigger:rpc:delete': 1,
                                'trigger:rpc:delete:args': ['owner', 'rule_name'],
                                'trigger:rpc:purge': 1,
                                'trigger:rpc:purge:args': ['owner'],
                                'trigger:rpc:list': 1,
                                'trigger:rpc:list:args': ['_filter'],
                                'trigger:event:ruleset_triggered': 1,
                                'trigger:event:ruleset_triggered:params': ['ruleset',
                                                                           'rules_stats']},
                            'require': [
                                'dependency_solver:rpc:explain > 0',
                                'dependency_solver:rpc:solve_dependencies > 0',
                                'overseer:rpc:get_service > 0',
                                'overseer:rpc:upgrade_service > 0',
                                'overseer:event:service_updated > 0',
                                'overseer:event:new_image > 0',
                                'scaler_docker:rpc:fetch_image_config > 0',
                                'scaler_docker:rpc:list_services > 0',
                                'scaler_docker:rpc:update > 0',
                                'load_manager:rpc:monitor_service > 0',
                                'overseer:rpc:scale > 0',
                                'trigger:rpc:delete > 0',
                                'trigger:rpc:compute > 0',
                                'trigger:rpc:add > 0',
                                'overseer:event:service_updated > 0',
                                '"metrics.exists" in monitorer_rabbitmq:event:metrics_updated:params',
                                'monitorer_rabbitmq:rpc:track >= 1']
                        }
                    }
                    },
                   ]
        s = Solver(catalog, tuple(), debug=True)
        result = list(s.solve())
        assert s.anomalies == []
        assert s.failed == []
        assert 1 == len(result)

        # explains
        s = Solver(catalog, tuple(), debug=True)
        result = s.explain()
        assert s.anomalies == []
        assert s.failed == []
        assert 0 == result


class TestExplain(object):

    def test_explain_1(self):
        catalog = [{'name': 'producer', 'versions': {'1.0.16': {'provide': {}, 'require': []}}},
                   {'name': 'consumer',
                    'versions': {'1.0.3': {'provide': {},
                                           'require': ['producer:rpc:echo', '"*args" in producer:rpc:echo:args']}}},
                   {'name': 'portainer', 'versions': {'latest': {'provide': {}, 'require': []}}}]
        s = Solver(catalog, tuple(), debug=True)

        result = list(s.solve())
        assert len(result) == 0

    def test_explain_uniqu(self):
        catalog = [{'name': 'producer', 'versions': {'1.0.16': {'provide': {}, 'require': []}}},
                   {'name': 'consumer',
                    'versions': {'1.0.3': {'provide': {},
                                           'require': []}}},
                   {'name': 'portainer', 'versions': {'latest': {'provide': {}, 'require': []}}}]
        s = Solver(catalog, tuple(), debug=True)

        result = list(s.solve())
        assert len(result) == 1


class TestPerfRealData(object):
    def load_sample(self, sample):
        with open(os.path.join(os.path.dirname(__file__), 'samples', sample)) as f:
            return json.load(f)

    def test_solve_dependency_1(self, dependency_solver: DependencySolver):
        payload = self.load_sample('sample1.json')
        result = dependency_solver.solve_dependencies(*payload)
        assert len(result['results']) == 96
        assert result['results'][-1] == {
            'http_to_rpc': '0.1.19',
            'joboffer_algolia_publisher': '0.1.24',
            'joboffer_fetcher': '0.1.22',
            'joboffer_xml_publisher': '0.1.19',
            'maiev': '1.2.0',
            'yupeeposting-backend': '0.2.55',
            'yupeeposting-webui': '0.2.56'}
        assert result['anomalies'] == []
        assert result['errors'] == []

    @pytest.skip("bad perfs prohibit this test")
    def test_solve_dependency_2(self, dependency_solver: DependencySolver):
        payload = self.load_sample('sample2.json')
        result = dependency_solver.solve_dependencies(payload)
        assert len(result['results']) == 96
        assert result['results'][-1] == {
            'http_to_rpc': '0.1.19',
            'joboffer_algolia_publisher': '0.1.24',
            'joboffer_fetcher': '0.1.22',
            'joboffer_xml_publisher': '0.1.19',
            'maiev': '1.2.0',
            'yupeeposting-backend': '0.2.55',
            'yupeeposting-webui': '0.2.56'}
        assert result['anomalies'] == []
        assert result['errors'] == []

    def test_solve_dep_no_service(self):
        catalog = self.load_sample('sample1.json')[0]
        s = Solver(catalog, [], debug=True)
        begin = time.time()
        solved = list(s.solve())
        end = time.time()

        assert len(solved) == 96
        assert solved[0] == {
            'http_to_rpc': '0.1.19',
            'joboffer_algolia_publisher': '0.1.24',
            'joboffer_fetcher': '0.1.19',
            'joboffer_xml_publisher': '0.1.24',
            'maiev': '1.2.0',
            'yupeeposting-backend': '0.2.62',
            'yupeeposting-webui': '0.2.57'}
        elapsed = end - begin
        assert elapsed < 25

    def test_solve_dep_memory_consumption(self):
        catalog = self.load_sample('sample1.json')[0]
        s = Solver(catalog, [], debug=True)
        solved = list(s.solve())
        assert len(solved) == 96
        encoded = json.dumps(solved).encode('utf8')
        assert len(encoded) < 1024 * 21  # 21k
