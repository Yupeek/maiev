# -*- coding: utf-8 -*-
import copy
import logging

from service.dependency_solver.dependency_solver import Solver

logger = logging.getLogger(__name__)


class TestSolver:
    CATALOG1 = [
        {
            "name": "service1",
            "versions": {
                1: {
                    "provide": {
                        "service1:event:ping": 1, "service1:rpc:hello": 1, "service1:rpc:hello:args": ["name"]
                    },
                    "require": []
                },
                2: {
                    "provide": {
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
        assert set(o.global_name for o in objects_['service1'].objects) == {'event', 'rpc'}
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
            res = tuple(
                (service['name'], version)
                for service, version in solution
            )
            assert expected == res

    def test_solve_extra1(self):
        s = Solver(self.CATALOG1, ("service1 == 2",))
        expected_solutions = [
            (('service1', 2), ('service2', 2)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            res = tuple(
                (service['name'], version)
                for service, version in solution
            )
            assert expected == res

    def test_solve_extra2(self):
        s = Solver(self.CATALOG1, ("service1 == 1",))
        expected_solutions = [
            (('service1', 1), ('service2', 1)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            res = tuple(
                (service['name'], version)
                for service, version in solution
            )
            assert expected == res

    def test_solve_not_possible(self):
        s = Solver(self.CATALOG1, ("not service1",))
        assert 0 == len(list(s.solve()))

    def test_insolvable(self):
        s = Solver(self.CATALOG_INSOLVABLE, ())
        expected_solutions = [
            (('db', 1), ('auth', 1)),
        ]

        for expected, solution in zip(expected_solutions, s.solve()):
            res = tuple(
                (service['name'], version)
                for service, version in solution
            )
            assert expected == res

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
            res = tuple(
                (service['name'], version)
                for service, version in solution
            )
            assert expected == res


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



