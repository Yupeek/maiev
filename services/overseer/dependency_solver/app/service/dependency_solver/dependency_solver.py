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

    def __init__(self, catalog, extra_constraints):
        self.catalog = catalog
        self.extra_constraints = extra_constraints

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

                res[service['name']][number] = compiled = []
                for require in version['require']:  # type: str
                    compiled.append(parse_manager.parse(require))
        self.extra_constraints_compiled = [
            parse_manager.parse(constr) for constr in self.extra_constraints
        ]
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
                })
            )

        yield from self.backtrack(variables, [self.check_requirements, self.check_extra_constraints], [])

    def check_requirements(self, service, version, tmpsolution):
        """
        check if given service for given version is valid for tmpsolution
        :param dict service:
        :param dict version:
        :param list[(dict, int)] tmpsolution:
        :return:
        """
        provided = self.build_provided(tmpsolution)
        try:
            return all(require(provided) for require in version['require'])
        except (ScopeError, KeyError) as e:
            return False

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
            return all(require(provided) for require in self.extra_constraints_compiled)
        except (ScopeError, KeyError) as e:
            return False

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

        for remaining_service, versions in remaining_services:
            for version_num, version in sorted(versions.items(), reverse=True):
                for c in constraints:
                    if not c(remaining_service, version, tmp_solution):
                        break
                else:
                    # all check passed
                    yield from self.backtrack(
                        remaining_services[1:],
                        constraints,
                        tmp_solution + [(remaining_service, version_num)]
                    )


class DependencySolver(BaseWorkerService):
    """
    this service use CSP and backtracking alogrithme to solve the best dependency for
    running service.

    rcp
    ###

    hello(name: string): string

    """
    name = 'overseer_dependency_solver'

    @rpc
    @log_all
    def solve_dependencies(self, catalog, extra_constraints=tuple()):
        """
        build all possibles revision for the given catalog respecting given constraints.

        :param list catalog: the catalog of micro-service, including there version, and for each the requirements and
                what they provides::

                    catalog:
                        service:
                            name: "myservice"
                            versions:
                                provide: {"rpc:holle": 1, "rpc:hello:args": ["name"]}
                                require: ["myservice:rpc:hello", "myservice:rpc:hello>1",
                                          "'name' in myservice:rpc:hello:args"]

        :param list extra_constraints: list of extra constraints if required (same form as service's require)
        :return: all possibles versions folowing the given constraints
        """
        s = Solver(catalog, extra_constraints)
        return list(s.solve())
