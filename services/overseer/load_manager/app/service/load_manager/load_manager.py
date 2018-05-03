# -*- coding: utf-8 -*-
import datetime
import logging

from nameko.events import SERVICE_POOL, event_handler
from nameko.exceptions import UnknownService
from nameko.rpc import RpcProxy, rpc
from nameko.timer import timer

from common.base import BaseWorkerService
from common.db.mongo import Mongo
from common.utils import log_all

logger = logging.getLogger(__name__)


class LoadManager(BaseWorkerService):
    """
    this service monitor load of service and manage their best scale.

    public events
    #############

    - service_update(dict):

    subscribe
    #########

    - otherService.event: v>1.1

    rcp
    ###

    hello(name: string): string

    """
    name = 'overseer_load_manager'

    trigger = RpcProxy('trigger')
    """
    :type: service.trigger.trigger.Trigger
    """
    mongo = Mongo(name)
    """
    :type: mongo.Mongo
    """

    overseer = RpcProxy('overseer')
    """
    :type: service.overseer.overseer.Overseer
    """

    @event_handler(
        'trigger', 'ruleset_triggered', handler_type=SERVICE_POOL
    )
    @log_all
    def on_ruleset_triggered(self, payload):
        """
        event send by the trigger service each time a ruleset has changed his state.
        expected payload ::

            {
                'ruleset': {'owner': ..., 'name': ..., },
                'rules_stats': {'rule1': True, 'rule2': False},
            }

        """
        assert set(payload.keys()) <= {'ruleset', 'rules_stats'}, \
            'the payload does not contains the required keys'
        ruleset = payload['ruleset']

        if ruleset.get('owner') == self.name and ruleset.get('name'):
            service = self._get_service(ruleset['name'])
            ruleset = payload['rules_stats']
            self._execute_ruleset(ruleset, service)

    @event_handler(
        'overseer', 'service_updated', handler_type=SERVICE_POOL
    )
    @log_all
    def on_service_updated(self, payload):
        service = payload.get('service')
        diff = payload.get('diff')
        my_service = self._get_service(service['name'])
        if my_service is None:
            return  # this service is not monitored by us

        if 'scale' in diff or 'mode' in diff:
            my_service['mode'] = service['mode']
        if 'scale_config' in diff:
            my_service['scale_config'] = service['scale_config']
            self._set_trigger_rules(service['name'], service['scale_config']['scale'])

        self.mongo.services.update(
            {'name': service['name']},
            my_service,
            upsert=True,
        )

    @timer(interval=15)
    @log_all
    def recheck_rules(self):
        now = datetime.datetime.now()
        for service in self._get_services():

            try:
                latest_ruleset = service['latest_ruleset']
                rule, date = latest_ruleset['rule'], latest_ruleset['date']
            except KeyError:
                continue
            if (rule['__scale_up__'] or rule['__scale_down__']) and \
                    (now - date).total_seconds() > 30:
                self._execute_ruleset(rule, service)

    @rpc
    @log_all
    def monitor_service(self, service):
        """
        monitor the given service.

        :param service: the service with his name and his scaler_config
        :return:
        """
        self.mongo.services.update(
            {'name': service['name']},
            service,
            upsert=True,
        )
        self._set_trigger_rules(service['name'], service['scale_config']['scale'])

    @rpc
    @log_all
    def unmonitor_service(self, service_name):
        self.mongo.services.delete_many({'name': service_name})
        self.trigger.delete(self.name, service_name)

    # #######################################
    # private database helpers
    # #######################################

    def _get_service(self, service_name):
        """
        return the service as stored in database. ie::

            {
                "scale_config": {
                    "scale": {
                        "rules": [
                            {"expression": "rmq:waiting == 0 or rmq:latency < 0.200", "name": "latency_ok"},
                            {"expression": "rmq:latency > 5", "name": "latency_fail"},
                            {"expression": "rmq:latency > 10 or (rules:latency_fail and
                                rules:latency_fail:since > \"25s\")", "name": "panic"},
                            {"expression": "rules:latency_ok and rules:latency_ok:since > \"30s\"",
                                "name": "stable_latency"}
                        ],
                        "scale_down": "rules:stable_latency and rmq:consumers > 0",
                        "scale_up": "rules:panic or (rmq:consumers == 0 and rmq:waiting > 0)  or not rmq:exists",
                        "resources": [{"monitorer": "monitorer_rabbitmq", "identifier": "rpc-producer", "name": "rmq"}]
                    }
                },
                "name": "producer",
                "latest_ruleset": {
                    "date": ISODate("2018-05-03T14:19:19.596Z"),
                    "rule": {
                        "latency_ok": true,
                        "latency_fail": false,
                        "panic": false,
                        "stable_latency": true, "__scale_up__": false,
                        "__scale_down__": true
                    }
                }
            }

        :param service_name:
        :return:
        """
        return self.mongo.services.find_one({'name': service_name})


    def _get_services(self):
        return self.mongo.services.find()

    # #######################################
    # privates functions
    # #######################################

    def _set_trigger_rules(self, service_name, scale_conf):
        """
        save and apply the trigger rules from the given service.

        :param scale_conf: the service to monitor. must be a dict of ::


        {
            "resources": [
                {
                    "name": str,  # the name of the ressource (used in bool expression)
                    "monitorer": str,  # the monitorer providing this ressource («rabbitmq_monitorer»)
                    "identifier": str,  # the identifier expected by the provider (queue name)
                }
            ],
            "rules": [
                {
                    "name": str,  # the name of the rule, for further usage via «rules:xx» and «rules:xx:since»
                    "expression": str # the boolean expression ie: "rmq:waiting == 0 or rmq:latency < 0.200"
                },
            ],
            "scale_up": str # the boolean expression to trigger a scale up ie: "rules:panic",
            "scale_down": str # the boolean expression to scale down. ie : "rules:stable_latency"
        }
        :return:
        """
        # now, we add the trigger config to scale automaticaly this service upon events.
        ruleset = self._create_trigger_ruleset(service_name, scale_conf)
        try:
            test = self.trigger.compute(ruleset)
            if test['status'] == 'success':
                self.trigger.add(ruleset)
            else:
                logger.error("imposible to add the ruleset %s: %s", ruleset, test)
        except UnknownService:
            logger.error("trigger service is not available. can't set the rules")

    def _execute_ruleset(self, ruleset_status, service):
        """
        execute the ruleset status by scaling the service
        :param ruleset_status: the ruleset status given by the trigger ie::
            {'latency_ok': True,
            'latency_fail': False,
            'panic': False,
            'stable_latency': False,
            '__scale_up__': False,
            '__scale_down__': False
            }

        :param dict service: the service to change
        """
        service['latest_ruleset'] = {"date": datetime.datetime.now(), "rule": ruleset_status}
        self.mongo.services.update(
            {'name': service['name']},
            service
        )

        if ruleset_status.get('__scale_up__'):
            delta = +1
        elif ruleset_status.get('__scale_down__'):
            delta = -1
        else:
            delta = 0

        current, best = self._get_best_scale(service, delta=delta)
        if current != best:
            logger.info("rules triggered new scale: %s => %s", current, best)
            self.overseer.scale(service['name'], scale=best)

    def _get_best_scale(self, service, delta=0):
        """
        return the best scale value for a service.
        :param service: the service to compute
        :param delta: the +1 or -1 if the service is in load or not
        :return: the current scale value and the best one
        :rtype: tuple(int, int)
        """
        mode = service.get('mode', {'name': 'replicated', 'replicas': 1})
        scale_config = service.get('scale_config') or {}

        if mode['name'] == 'replicated':
            current = mode['replicas']

            # TODO: compute for load here
            best = current + delta
            # respect max/min from scale_config
            best = max((best, scale_config.get('min', 0)))
            best = min((best, scale_config.get('max', 99)))
            return current, best
        else:
            return None, None

    def _create_trigger_ruleset(self, service_name, scale_conf):
        """
        create the trigger ruleset for the given service
        :param service:
        :return:
        """

        rules = []
        for rule in scale_conf.get('rules', ()):
            if rule['name'] in ("__scale_up__", "__scale_down__"):
                logger.warning('scale_config contains reserved rule name %s. this one is ignored', rule['name'])
            else:
                rules.append(rule)
        if 'scale_up' in scale_conf:
            rules.append({
                'name': '__scale_up__',
                'expression': scale_conf['scale_up']
            })
        if 'scale_down' in scale_conf:
            rules.append({
                'name': '__scale_down__',
                'expression': scale_conf['scale_down']
            })

        return {
            'owner': self.name,
            'name': service_name,
            'resources': scale_conf.get('resources', ()),
            'rules': rules
        }
