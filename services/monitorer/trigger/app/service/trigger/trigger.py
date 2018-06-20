# -*- coding: utf-8 -*-
import datetime
import logging
from functools import partial

import pymongo
import pyparsing
from booleano.operations.operands.constants import Constant
from booleano.operations.variables import BooleanVariable, DurationVariable
from booleano.parser.core import EvaluableParseManager
from booleano.parser.grammar import Grammar
from booleano.parser.scope import Bind, SymbolTable
from nameko.events import EventDispatcher, event_handler
from nameko.rpc import rpc

from common.base import BaseWorkerService
from common.db.mongo import Mongo
from common.dp.generic import GenericRpcProxy
from common.entrypoint import once
from common.utils import filter_dict, log_all

logger = logging.getLogger(__name__)


# TODO: check for ming to apply a structure to our db
# http://ming.readthedocs.io/en/latest/userguide.html

TYPINGS = """
from typing import Dict, List, Any
import datetime

Rule = Dict[str, str]


RuleSet = {
    "id": str,  # id of the rule (for db udpate)
    "owner": str,  # the name of the service that own this ruleset
    "name": str,  # the name of the ruleset
    "resources": List[ # the list of resources that is used for this parsing (set of metrics)
        {
            "name": str,  # the name of the ressource (given by the service,
                          # used for expression reference ie: «mq:latency»)
            "monitorer": str,  # name of the monitorer that provide this ressource (monitorer_rabbitmq)
            "identifier": str,  # the identifier used by the monitorer. can be meaningless to us
            "history": {
                "last_metrics": Dict[str, Any],  # the last metrics for thir resources
                "date": datetime.datetime,  # the last date of this ressource
            }
        }
    ],
    "rules": List[
        {
            "name": str,  # the name of the rule, used for cross-reference via «rules.**thisname**»
            "expression": str,  # the boolean expression to resolve for this rule
            "history": {
                "last_result": bool,  # the last result of this rule
                "date": datetime.datetime,  # the date at which the last result was dated
            }
        }
    ]
}

MetricsPayload = {
    "monitorer": str,  # the monitorer for this metrics
    "identifier": str,  # the meaningless identifier for this metrics
    "metrics": {
        "waiting": int,  # the number of waiting work
        "latency": float,  # the current latency
        "rate": float,  # the real rate (>0 mean taking retard, <0 mean emptying queue)
        "call_rate": float,  # the rate at which the ressource is used
        "exec_rate": float,  # the rate at which the worker empty the queue
        "consumers": int,  # the number of consumer for this work
    }
}
"""
grammar = Grammar(**{
    "belongs_to": "in",
    "and": 'and',
    "or": 'or',
    "not": "not",
})


def get_since(ctx, rule_name, rule):
    """
    return the since date for a given rule.
    if the current result match the value in the history, it return the date of the history
    else it return now (history absent or value mismatch)

    :param ctx:  the context in which the current value is present (or not)
    :param rule_name:  the name of the rule (as inserted into the context)
    :param rule: the rule itself, in whth the history is stored
    :return:
    """
    history = rule.get('history', {})
    last_result = history.get("last_result")
    current = ctx.get(rule_name)
    if last_result is None or (current is not None and last_result != current):
        return datetime.timedelta(seconds=0)
    else:
        return get_now() - history['date']


def get_now():
    # cant be offset aware from now, since mongodb don't support it
    return datetime.datetime.now()


def get_rule_result(ctx, rule_name, rule):
    """
    return the result of a rule. firt check if present into ctx, else search into the rule history

    :param ctx: the context in which the history may be present
    :param rule_name: the name of the rule as used to search in ctx
    :param rule: the rule to use. used to search throught his history
    :return:
    """
    result = ctx.get(rule_name)
    if result is None:
        result = rule.get('history', {}).get('last_result', False)
    return result


class Trigger(BaseWorkerService):
    """
    a service that will listen to all incoming events and compute them with
    boolean rules. finaly, it will dispatch events with resulting value.

    each rules is pushed by other services.

    public events
    #############

    - ruleset_value_changed(rules_with_values)

    subscribe
    #########

    - monitorer_rabbitmq.metirc_update(metrics: dict)

    rpc
    ###

    compute(Ruleset, values)
    add(Ruleset)
    delete(rule_id)
    purge(owner)
    list(filter)

    """

    name = 'trigger'
    mongo = Mongo()
    """
    :type: pymongo.MongoClient
    the mongo database.

    tables
    ######

    rulesets
    --------

    contains all rulesets in the same database.

    must respect :type:`RuleSet`

    """

    dispatch = EventDispatcher()

    monitorer_rpc = GenericRpcProxy()

    # ####################################################
    #                 ONCE
    # ####################################################

    @once
    @log_all
    def create_index(self):
        self.mongo.rulesets.create_index([
            ('owner', pymongo.ASCENDING),
            ('name', pymongo.ASCENDING),
        ],
            unique=True,
            background=True
        )

    # ####################################################
    #                 EVENTS
    # ####################################################

    @event_handler(
        "monitorer_rabbitmq", "metrics_updated", reliable_delivery=False
    )
    @log_all
    def on_metrics_updated(self, payload):
        """
        each time monitorer_rabbitmq publish mew metrics, we find if we monitor this data and
        then compute the rules against this metrics.

        :param MetricsPayload payload: the payload of the event.
        :return:
        """
        assert set(payload.keys()) <= {'monitorer', 'identifier', 'metrics'}, \
            'the payload does not contains the required keys'

        q = {'resources.monitorer': payload['monitorer'], 'resources.identifier': payload['identifier']}

        for ruleset in self.mongo.rulesets.find(q):
            for resource in ruleset['resources']:
                if resource['monitorer'] == payload['monitorer'] and resource['identifier'] == payload['identifier']:
                    self._save_metrics(ruleset, resource, payload['metrics'])
            try:
                results = self._compute_ruleset(ruleset)
            except Exception as e:
                logger.exception("error while executing ruleset : %r: %s", ruleset, e)
            else:
                if results is None:
                    logger.debug("not enouth metrics to computes the ruleset %s" % ruleset['name'])
                else:
                    updated = False
                    for rule in ruleset['rules']:
                        updated = self._save_rules_results(ruleset, rule, results[rule['name']]) or updated
                    # if one rule has been saved (and so changed the history)
                    if updated:
                        event_payload = {
                            'ruleset': self._validate_ruleset(ruleset),
                            'rules_stats': results
                        }
                        logger.debug("triggering event 'ruleset_trigger' %s" % results)
                        self.dispatch('ruleset_triggered', event_payload)

    # ####################################################
    #                 RPC
    # ####################################################

    @rpc
    @log_all
    def compute(self, ruleset):
        """
        compute the ruleset. it will use the history of each metrics to compute the
        ruleset. the history can be given along with the ruseset to try
        a custom metrics
        :param RuleSet ruleset:
        :return:
        """
        try:
            validated_ruleset = self._validate_ruleset(ruleset)
        except KeyError as e:
            return {
                "status": "error",
                "exception": "missing key for ruleset : %s" % e,
                "exception_type": str(type(e).__name__),
                "result": None,
                "exception_extra": {}
            }
        except Exception as e:
            return {
                "status": "error",
                "exception": "error : %s" % e,
                "exception_type": str(type(e).__name__),
                "result": None,
                "exception_extra": {k: v for k, v in e.__dict__.items()
                                    if isinstance(v, (str, float, int)) and k != 'msg'}
            }

        if not validated_ruleset['resources']:
            return {
                "status": "error",
                "exception": "can't add ruleset without bound resources to monitor",
                "exception_type": "ValueError",
                "result": None,
                "exception_extra": {}
            }
        try:
            result = self._compute_ruleset(validated_ruleset)
        except Exception as e:
            return {
                "status": "error",
                "exception": str(e),
                "exception_type": str(type(e).__name__),
                "result": None,
                "exception_extra": {k: v for k, v in e.__dict__.items()
                                    if isinstance(v, (str, float, int)) and k != 'msg'}
            }
        else:
            return {
                "status": "success",
                "result": result
            }

    @rpc
    @log_all
    def add(self, ruleset):
        """
        add a ruleset into the list of managed ruleset.
        all ruleset will be keep unique by owner and name. 2 add for the
        same owner and name will replace the existing one
        :param RuleSet ruleset:
        :return:
        """
        logger.debug("added ruleset %s", {'owner': ruleset['owner'], 'name': ruleset['name']})
        ruleset = self._validate_ruleset(ruleset)
        self.mongo.rulesets.replace_one(
            {'owner': ruleset['owner'], 'name': ruleset['name']},
            ruleset,
            upsert=True,
        )
        # ask for monitorer to provide queue ressources datas
        for resource in ruleset['resources']:
            self.monitorer_rpc.get(resource['monitorer']).track(resource['identifier'])

    @rpc
    @log_all
    def delete(self, owner, rule_name):
        self.mongo.rulesets.delete_many({
            'owner': owner,
            'name': rule_name
        })

    @rpc
    @log_all
    def purge(self, owner):
        self.mongo.rulesets.delete_many({
            'owner': owner
        })

    @rpc
    @log_all
    def list(self, _filter=None, **filter):
        """
        return all ruleset matching the given filters.
        the filters can be given via keyword, or via the positonal argument _filter.
        :param dict _filter: like keywords: the search term compatible with pymongo
        :keyword:  like _filter: the search term compatible with pymongo
        :return: the list of filtered RuleSet
        :rtype: list[RuleSet]
        """

        return [
            filter_dict(ruleset)
            for ruleset in (self.mongo.rulesets.find(_filter or filter) or ())
        ]

    # ####################################################
    #                 PRIVATE
    # ####################################################

    def _save_metrics(self, ruleset, ressource, metrics):
        """
        save the metric in the history of resource in ruleset
        :param ruleset: the ruleset to save in mongodb (update)
        :param ressource: the resource to modify by side effect
        :param metrics: the metric to save into the bases.
        :return:
        """
        if ressource.get('history', {}).get('last_metrics') == metrics:
            return False
        ressource['history'] = {
            'last_metrics': metrics,
            'date': get_now()
        }
        self.mongo.rulesets.update_one(
            {
                '_id': ruleset['_id'],
                'ressource.name': ressource['name']
            }, {
                "$set": {
                    "ressource.$.history": ressource['history']
                }
            }
        )
        return True

    def _save_rules_results(self, ruleset, rule, result):
        """
        save the rule result and the current date if this result has changed.
        :param ruleset: the ruleset to save in mongodb
        :param rule:  the rule to modify by side effect
        :param result: the current result to save
        :return:
        """
        if rule.get('history', {}).get('last_result') == result:
            return False
        rule['history'] = {
            'last_result': result,
            'date': get_now()
        }
        self.mongo.rulesets.update_one({
            '_id': ruleset['_id'],
            'rules.name': rule['name']
        }, {
            "$set": {
                "rules.$.history": rule['history']
            }
        })
        return True

    def _validate_ruleset(self, ruleset):
        """
        create a copy of the given ruleset with only the used values.
        :param ruleset: a RuleSet compatible dict
        :return: a ready to save ruleset
        :raise KeyError: if a mandatory field is missing
        """
        return {
            "owner": ruleset['owner'],
            "name": ruleset['name'],
            "resources": [
                {
                    "name": ressource['name'],
                    "monitorer": ressource['monitorer'],
                    "identifier": ressource['identifier'],
                    "history": {k: v for k, v in ressource.get('history', {}).items() if k in ("last_metrics", "date")}
                }
                for ressource in (ruleset.get("resources") or ())
            ],
            "rules": [
                {
                    "name": rule['name'],
                    "expression": rule['expression'],
                    "history": {k: v for k, v in rule.get('history', {}).items() if k in ("last_result", "date")}
                }
                for rule in ruleset.get('rules', [])
            ],
        }

    def _get_ruleset(self, owner, name):
        return self.mongo.rulesets.find_one({'owner': owner, 'name': name})

    def _compute_ruleset(self, ruleset):
        """
        compute the ruleset with the metrics from the ruleset history
        if a history is not populated, this method will return None,
        and will do so until all resources are populated

        :param Ruleset ruleset:  the ruleset fetched for this metrics
        :return:
        """
        # build all asked resources for this ruleset
        metrics = {}
        for ressource in ruleset["resources"]:
            val = ressource.get('history', {}).get('last_metrics')
            if not val:
                return
            metrics[ressource['name']] = val

        return self._solve_rules(
            ruleset['rules'],
            metrics
        )

    def _solve_rules(self, rules, metrics):
        """
        solve the rules using the given metrics.
        metrics must contains all needed metrics.
        :param list[Rule] rules: the
        :param metrics:
        :return:
        :raises:
            pyparsing.ParseException
        """
        results = {}

        root_table = SymbolTable('root', ())

        for metric_name, values in metrics.items():
            # bind to allow "rmq & rmq:xxx"
            root_table.add_object(Bind(metric_name, Constant(bool(values))))
            # bind to allow "rmq:latency" etc
            root_table.add_subtable(SymbolTable(
                metric_name,
                tuple(Bind(k, Constant(v)) for k, v in values.items())
            ))
        # build the symbol table for all rules (as boolean)
        rules_symbols = SymbolTable('rules', ())

        root_table.add_subtable(rules_symbols)
        for rule in rules:
            rule_name_ = rule['name']

            rules_symbols.add_object(
                Bind(rule_name_, BooleanVariable(partial(get_rule_result, rule_name=rule_name_, rule=rule)))
            )
            rules_symbols.add_subtable(
                SymbolTable(
                    rule_name_,
                    (
                        Bind('since', DurationVariable(partial(get_since, rule_name=rule_name_, rule=rule))),
                    )
                )
            )

        parse_manager = EvaluableParseManager(root_table, grammar)

        for rule in rules:

            expression_ = rule['expression']
            try:
                results[rule['name']] = parse_manager.parse(expression_)(results)
            except pyparsing.ParseException as e:
                logger.debug("error while parsing %r: %s", expression_, e)
                raise
        return results
