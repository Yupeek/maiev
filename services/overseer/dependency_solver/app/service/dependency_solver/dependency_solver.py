#!/bin/env python
# -*- coding: utf-8 -*-

import logging
from functools import partial

from booleano.exc import ScopeError
from booleano.operations.variables import BooleanVariable, variable_symbol_table_builder
from booleano.parser import Bind, Grammar, SymbolTable
from booleano.parser.core import EvaluableParseManager
from nameko.rpc import rpc

from common.base import BaseWorkerService
from common.utils import log_all

logger = logging.getLogger(__name__)

grammar = Grammar(**{
    "belongs_to": "in",
    "and": 'and',
    "or": 'or',
    "not": "not",
})


def check_exists(context, service_name):
    """
    check if service_name is included in context
    :param dict context: the context
    :return:
    """
    return service_name in context


def split_path(path):
    """
    take a path (service:rpc:method) and return the path (service:rpc) and the method name)
    :param str path:
    :return: the tiple with path[str] and method[str]
    """
    splited = path.split(":")
    return ":".join(splited[:-1]), splited[-1]


def build_subtable(path, root_table):
    """
    build a chained subtable for the given path
    :param path: the path to build
    :param SymbolTable root_table: the root table in which we will add our table
    :return:
    """

    part = path[0]
    for st in root_table.subtables:
        if st.global_name == part:
            break
    else:
        st = SymbolTable(part, [])
        root_table.add_subtable(st)

    if path[1:]:
        return build_subtable(path[1:], st)
    else:
        return st


def complete_with_objects(root_table):
    """
    fill the given table and all subtalbse with objects checking if the context contains anything with this name.
    :param SymbolTable root_table: the symboltable to update and add objects.
    :return:
    """
    names = {o.global_name for o in root_table.objects}
    for st in root_table.subtables:
        if st.global_name not in names:
            root_table.add_object(Bind(
                st.global_name,
                BooleanVariable(partial(check_exists, service_name=st.global_name))
            ))
            complete_with_objects(st)


class Solver(object):

    def __init__(self, catalog, extra_constraints, debug=False):
        self.catalog = catalog
        self.extra_constraints = extra_constraints
        self.anomalies = []
        self.debug = debug
        self.failed = []
        self.extra_constraints_compiled = []

    def compile_resolution(self):
        pass

    def compile_symbole_table(self):
        """
        build the symbol table using all «provide» of all services/versions
        :return:
        """

        res = SymbolTable("root", [])
        for service in self.catalog:

            for number, version in service['versions'].items():
                for provide, value in version['provide'].items():  # type: (str, int)
                    path, object = split_path(provide)
                    subtable = build_subtable(path.split(':'), res)
                    variable_name = '%s:%s' % (path, object)
                    try:
                        vartype = variable_symbol_table_builder.find_for_type(type(value))
                        subtable.add_object(
                            Bind(object, vartype(variable_name))
                        )
                    except ScopeError:
                        pass
        complete_with_objects(res)
        return res

    def compile_conditions(self, symbol_tables):
        """
        build all Variables with their compiler boolean expressions
        conditions is a dict with (service_name, version) as key and list(conditions) as values.
        :return: dict of [services][versions] => [complied parse tree]
        :rtype: dict(str, dict(int, list(ParseTree)))
        """
        parse_manager = EvaluableParseManager(symbol_tables, grammar)

        res = {}
        for service in self.catalog:
            res[service['name']] = {}

            for number, version in service['versions'].items():
                require = None
                try:
                    compiled = []
                    for require in version['require']:  # type: str

                        parsed = parse_manager.parse(require)
                        parsed.original_string = require
                        compiled.append(parsed)
                    res[service['name']][number] = compiled
                except ScopeError as e:
                    self.anomalies.append({
                        "expression": require,
                        "service": service['name'],
                        "version": number,
                        "error": str(e)
                    })

        self.extra_constraints_compiled = []
        for constr in self.extra_constraints:
            parsed = parse_manager.parse(constr)
            parsed.original_string = constr
            self.extra_constraints_compiled.append(parsed)

        return res

    def solve(self):
        symbol_table = self.compile_symbole_table()
        conditions = self.compile_conditions(symbol_table)
        # condition service: version: [conditions]
        # first: we build the variables.
        variables = [
            # (servicename: str, versions: {provide: dict, require: condition})
        ]
        for service in self.catalog:
            variables.append(
                (service, {
                    number: {
                        "provide": version['provide'],
                        "require": conditions[service['name']][number]
                    }
                    for number, version in service["versions"].items()
                    if number in conditions.get(service['name'], {})
                })
            )
        encountered_solutions = [
        ]
        for solution in self.backtrack(variables, [self.check_requirements, self.check_extra_constraints], []):
            pined = {
                pin[0]['name']: pin[1]
                for pin in solution
            }
            if pined in encountered_solutions:
                continue
            encountered_solutions.append(pined)
            yield solution

    def explain(self):
        """
        just render one solution with all version at once
        catalog must be provided with only one version for all services.
        :return:
        """
        symbol_table = self.compile_symbole_table()
        conditions = self.compile_conditions(symbol_table)

        phase = []
        for service in self.catalog:
            if len(service['versions']) != 1:
                raise Exception("you must provide only one version for service %s to explain this phase. got %s" %
                                (service['name'], list(service['versions'])))
            number, version = list(service['versions'].items())[0]
            if number in conditions.get(service['name'], {}):
                phase.append((service, number, {
                    "provide": version['provide'],
                    "require": conditions[service['name']][number]
                }))

        failed = 0

        for remaining_service, _, version in phase:

            for c in (self.check_requirements, self.check_extra_constraints):
                if not c(remaining_service, version, [s[:2] for s in phase]):
                    failed += 1

        return failed

    def check_requirements(self, service, version, tmpsolution):
        """
        check if given service for given version is valid for tmpsolution
        :param dict service:
        :param dict version:
        :param list[(dict, int)] tmpsolution:
        :return:
        """
        provided = self.build_provided(tmpsolution)
        require = None
        try:

            for require in version['require']:
                if not require(provided):
                    if self.debug:
                        self.failed.append({
                            "expression": require.original_string,
                            "service": service['name'],
                            "provided": provided
                        })
                    return False
        except (ScopeError, KeyError) as e:
            if self.debug:
                self.failed.append({
                    "expression": require.original_string,
                    "service": service['name'],
                    "provided": provided
                })
            self.anomalies.append({
                "expression": require.original_string,
                "service": service['name'],
                "error": repr(e)
            })
            return False
        else:
            return True

    def check_extra_constraints(self, service, version, tmpsolution):
        """
        check if given service for given version is valid for tmpsolution
        :param dict service:
        :param dict version:
        :param list[(dict, int)] tmpsolution:
        :return:
        """
        provided = self.build_provided(tmpsolution)
        try:
            for require in self.extra_constraints_compiled:
                if not require(provided):
                    if self.debug:
                        self.failed.append((require.original_string, provided))
                    return False
        except (ScopeError, KeyError) as e:
            return False
        else:
            return True

    def build_provided(self, solution):
        res = {}
        for s in solution:
            service, version_number = s
            res.update(service['versions'][version_number]['provide'])
            res.setdefault(service['name'], version_number)
        return res

    def backtrack(self, remaining_services, constraints, tmp_solution):
        if len(remaining_services) == 0:
            yield tmp_solution
        for i, (remaining_service, versions) in enumerate(remaining_services):

            for version_num, version in sorted(versions.items(), reverse=True):
                living_solution = tmp_solution + [(remaining_service, version_num)]
                for c in constraints:
                    if not c(remaining_service, version, living_solution):
                        break
                else:
                    # all check passed
                    yield from self.backtrack(
                        remaining_services[:i] + remaining_services[i + 1:],
                        constraints,
                        living_solution
                    )


class DependencySolver(BaseWorkerService):
    """
    this service use CSP and backtracking alogrithme to solve the best dependency for
    running service.

    rpc
    ###

    hello(name: string): string

    """
    name = 'dependency_solver'

    @rpc
    @log_all
    def solve_dependencies(self, catalog, extra_constraints=tuple(), debug=False):
        """
        build all possibles phases for the given catalog respecting given constraints.

        :param list catalog: the catalog of micro-service, including there version, and for each the requirements and
                what they provides::

                    -   name: "myservice"
                        versions:
                            $version:
                                provide: {"rpc:holle": 1, "rpc:hello:args": ["name"]}
                                require: ["myservice:rpc:hello", "myservice:rpc:hello>1",
                                          "'name' in myservice:rpc:hello:args"]

        :param list extra_constraints: list of extra constraints if required (same form as service's require)
        :return: all possibles versions folowing the given constraints.
        :rtype:   list of tuple with [0]=service data , [1]=version
        """
        try:
            s = Solver(catalog, extra_constraints, debug=debug)
            return {
                "results": list(s.solve()),
                "errors": [],
                "anomalies": s.anomalies
            }
        except ScopeError as e:
            logger.exception("scope error")
            return {
                "results": [],
                "errors": [
                    {"type": "missing scope",
                     "str": str(e)
                     }
                ]
            }

    @rpc
    @log_all
    def explain(self, catalog, extra_constraints=tuple()):
        """
        try only one possiblitiy and return if it's a valid phase or not.
        if it's not valid, return the failed requirements.
        :param catalog:
        :return:
        """
        s = Solver(catalog, extra_constraints, debug=True)
        try:
            return {
                "results": s.explain(),
                "errors": [],
                "anomalies": s.anomalies,
                "failed": s.failed
            }
        except ScopeError as e:
            logger.exception("scope error")
            return {
                "results": None,
                "anomalies": s.anomalies,
                "failed": s.failed,
                "errors": [
                    {"type": "missing scope",
                     "str": str(e)
                     }
                ]
            }
