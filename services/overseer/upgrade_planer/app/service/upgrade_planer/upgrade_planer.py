# -*- coding: utf-8 -*-
import copy
import datetime
import logging
from collections import namedtuple
from copy import deepcopy
from pprint import pprint

import pymongo
from nameko import timer
from nameko.events import SERVICE_POOL, EventDispatcher, event_handler
from nameko.rpc import RpcProxy, rpc
from semantic_version import Version

from common.base import BaseWorkerService
from common.db.mongo import Mongo
from common.entrypoint import once
from common.utils import ImageVersion, filter_dict, log_all

logger = logging.getLogger(__name__)


def accept_all(version, service):
    """
    accept all version for the catalog computing
    """
    return version.get('available', True)


def no_downgrade(version, service):
    if version == 'latest' or version['version'] == 'latest':  # always upgrade if it's latest version available
        return version.get('available', True)
    if service['version'] == 'latest':
        return False
    new_v = Version.coerce(version['version'])
    current_version = Version.coerce(service['version'])

    # always provide current version
    # or new version is an upgrade and is availble
    return new_v == current_version \
        or (new_v >= current_version and version.get('available', True))


def static_version(phase):
    """
    build a filter for build_catalog that will only yield given version in phase
    :param phase:
    :return:
    """

    def filter_(version, service):
        try:
            return phase[service['name']] == version['version']
        except KeyError:
            return False

    return filter_


# list of all filter for catalog
NO_DOWNGRADE = "no_downgrade"
ACCEPT_ALL = "accept_all"

# list of state for scheduled

RUNNING = 'running'
ABORDED = 'aborded'
WAITING = 'waiting'
DONE = 'done'

CATALOG_FILTERS = {
    NO_DOWNGRADE: no_downgrade,
    ACCEPT_ALL: accept_all
}

PhasePin = namedtuple('PhasePin', 'service,version')
PhasePin.__repr__ = lambda self: "PhasePin(service={},version={}".format(
    self.service.get('name', self.service), self.version)
Step = namedtuple('Step', 'service,from_,to')


class Phase(list):
    """
    a Phase is a list of PhasePin that represent a whole ensemble of services with one version.
    a Phase can be compatible or not.
    """

    @classmethod
    def deserialize(cls, remote_data):
        """
        deserialize the result from dependency_solver
        :param list[tuple[any, str]] remote_data:
        :return:
        """
        return cls(
            PhasePin(*i)
            for i in remote_data
        )


def _abord_scheduled(sched):
    """
    update the scheduler to abord it
    :param sched:
    :return:
    """
    sched['state'] = ABORDED
    for step in sched:
        if step['state'] == WAITING:
            step['state'] = ABORDED


class UpgradePlaner(BaseWorkerService):
    """
    this service plane and execute upgrade from a ecosystem status to another.

    public events
    #############

    - service_update(dict):

    subscribe
    #########

    - otherService.event: v>1.1

    rpc
    ###

    hello(name: string): string

    """
    name = 'upgrade_planer'

    mongo = Mongo(name)
    """
    :type: pymongo.MongoClient

    collections:
    ***********

    catalog
    #######

    list all managed service for auto upgrade

    name: producer
    version: 1.0.16
    service: # same struct as overseer
      name: producer
      image:
        type: docker
        image_info:
          repository: localhost:5000
          image: maiev
          tag: producer-1.0.16
          species: producer
          version: 1.0.16
          digest: sha256:581647ffd59fc7dc9b2f164fe299de29bf99fb1cb304c41ea07d8fa3f95f052b
        full_image_id: localhost:5000/maiev:producer
        available: true # boolean if the image is available
      scale_config:
      mode:
        name: replicated
        replicas: 23
    versions:
      1.0.1:
        version: 1.0.1
        dependencies:  # scale config data
          require: [...]
          provide: {...}

    history
    #######

    list all history of phases of services.

    services:
        $name: version
    date: $now


    scheduling
    ##########

    store all scheduled upgrades available.

    state: (running, aborded, done, waiting)
    steps:
      - service: $servicename
        from: $version_from
        to: $version_to
        state: (running, aborded, done, waiting)



    """

    dispatch = EventDispatcher()

    dependency_solver = RpcProxy("dependency_solver")
    """
    :type: service.dependency_solver.dependency_solver.DependencySolver
    """
    overseer = RpcProxy('overseer')
    """
    :type: service.overseer.overseer.Overseer
    """

    # ####################################################
    #   ONCE
    # ####################################################

    @once
    @rpc
    @log_all
    def sanity_check(self):
        """
        do some check about the database to prevent problemes for resolution
        :return:
        """
        for service in (self._unserialize_service(s) for s in self.mongo.catalog.find()):
            try:
                versions = service['versions']
                if not service['version'] in service['versions']:
                    logger.error(
                        "the service is fixed to a version which is not listed in available versions\n%s not in %s",
                        service['version'], versions
                    )
                    # call back overseer to get info about current version.
                    overseer_service = self.overseer.get_service(service['name'])
                    o_version_number = overseer_service['image']['image_info']['version']
                    scale_config_ = overseer_service['scale_config'] or {}
                    service['versions'][o_version_number] = {
                        "version": o_version_number,
                        "image_info": overseer_service['image']['image_info'],
                        "dependencies": scale_config_.get('dependencies', {}),
                        "available": True,
                    }
                    service['version'] = o_version_number
                    self._save_service(service)

                    logger.error("resolved previous error with call back to overseer: got version %s data",
                                 o_version_number)
            except Exception:
                logger.exception("error while scaning sanity of %s", service.get('name', '<noname>'))

    @once
    @log_all
    def create_index(self):
        self.mongo.catalog.create_index([
            ('name', pymongo.ASCENDING),
        ],
            unique=True,
            background=True
        )

    # ####################################################
    # Event handling
    # ####################################################

    @event_handler(
        "overseer", "service_updated", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def on_service_deployed(self, payload):
        """
        a new version of the current service is deployed. this event is triggered many times since
        a seervice can be updated with his: image,state,replica, etc
        :param payload:
        :return:
        """
        logger.debug("got notified by overseer.service_updated: %s", payload)
        assert {'service', 'diff'} <= set(payload), "missing data in payload: %s" % str(set(payload))

        service_name_ = payload['service']['name']
        service = self._get_service(service_name_)
        version_ = payload['service']['image']['image_info']['version']
        logger.info("new service deployed %s=%s", service_name_, version_)
        if service:
            from_version = service['version']
            upsert = from_version != version_
            service['service'] = payload['service']
            service['version'] = version_
        else:
            from_version = None
            scale_config_ = payload['service']['scale_config'] or {}
            service = {
                "name": service_name_,
                "service": payload['service'],
                "versions": {
                    version_: {
                        "version": version_,
                        "image_info": payload['service']['image']['image_info'],
                        "dependencies": scale_config_.get('dependencies', {}),
                        "available": True
                    }
                },
                "version": version_
            }
            upsert = True
        if upsert:
            self._save_service(service)

            self.mongo.phases.insert_one({
                "updated": service['name'],
                "from": from_version,
                "to": version_,
                "services": {
                    s['name']: s['version']
                    for s in self.mongo.catalog.find()
                },
                "date": datetime.datetime.now()
            })

        # we just handle finished changes: complited event or update of 0 replicas service
        completed_ = payload['diff'].get('state', {}).get('to') == 'completed'
        replicas_ = payload['service']['mode'] == {'name': 'replicated', 'replicas': 0}
        if from_version == version_:
            logger.debug("stayed at version %s: this is not an upgrade", from_version)
        elif completed_ or replicas_:
            logger.debug("continue plans: <completed_=%s replicas_=%s>", completed_, replicas_)
            self.continue_scheduled_plan(service, from_version, version_)
        else:
            logger.debug("notification inused: <completed_=%s replicas_=%s>", completed_, replicas_)

    @event_handler(
        "overseer", "cleaned_image", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def on_image_cleaned(self, payload):
        """
        triggered when the registry don't hold this version anymore.
        we update this version to tag it as unavailable
        :return:
        """
        logger.debug("cleaned image: %s", payload)
        assert {'service', 'image'} <= set(payload), "missing data in payload: %s" % str(set(payload))

        service_name_ = payload['service']['name']
        service = self._get_service(service_name_)

        version_number = payload['image']['version']
        if service and version_number in service['versions']:
            service['versions'][version_number]['available'] = False
            self._save_service(service)
            logger.debug("version %s of service %s tagged as unavailable", version_number, service_name_)
            if service['version'] == version_number:
                # this is the running process wihch don't have the image anymore
                logger.warning("currently running image %s was deleted from the repository. "
                               "the service %s will be unable to launch new instance without this image.",
                               payload['image'], service_name_)

    @event_handler(
        "overseer", "new_image", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def on_new_version(self, payload):
        logger.debug("new image: %s", payload)
        assert {'service', 'image', 'scale_config'} <= set(payload), "missing data in payload: %s" % str(set(payload))

        service_name_ = payload['service']['name']
        service = self._get_service(service_name_)

        version_number = payload['image']['version']
        image_info_ = payload['service']['image']['image_info']
        scale_config_ = payload['scale_config'] or {}
        if service:
            existing_version = service['versions'].get(version_number)
            if existing_version and existing_version['available'] and \
                    existing_version.get('dependencies') == scale_config_.get('dependencies'):
                return  # same image for same dep: this is same call for same image
        else:
            service = {
                "name": service_name_,
                "service": payload['service'],
                "versions": {},
                "version": image_info_['version']
            }

        new_version = service['versions'][version_number] = {
            "version": version_number,
            "image_info": payload['image'],
            "dependencies": scale_config_.get('dependencies', {}),
            "available": True
        }

        self._save_service(service)

        logger.debug("upserted %s => %r", service_name_, service)
        self.dispatch("new_version", {
            "service": filter_dict(service),
            "new": new_version
        })

    @event_handler(
        "upgrade_planer", "new_version", handler_type=SERVICE_POOL, reliable_delivery=True
    )
    @log_all
    def on_new_version_check_upgrade(self, payload):
        """
        each time a new version for a monitored service is released, we check if we can upgrade it
        :param payload:
        :return:
        """
        logger.debug("new version for %s: %s", payload['service']['name'], payload['new']['version'])
        self.run_available_upgrade()

    # ############################################
    #  RPC
    # ############################################

    @rpc
    @log_all
    def list_catalog(self, filter_=None):
        filter_ = filter_ or {}
        return [filter_dict(self._unserialize_service(res)) for res in self.mongo.catalog.find(filter_)]

    @rpc
    @log_all
    def list_scheduling(self, filter_=None):
        filter_ = filter_ or {}

        return [filter_dict(s) for s in self.mongo.scheduling.find(filter_)]

    @rpc
    @log_all
    def list_phases(self, filter_=None):
        filter_ = filter_ or {}

        return [filter_dict(s) for s in self.mongo.phases.find(filter_)]

    @rpc
    @log_all
    def explain_phase(self, phase: dict):
        """
        explain a phase and return if it's available or not, and if not why.
        :param dict phase: the dict with service.name => version
        :return:
        """

        catalog = self.build_catalog(static_version(phase))
        missing = []
        for service in catalog:
            if not service['versions']:
                missing.append(service['name'])
        if missing:
            raise Exception(
                "the catalog contains %d services without valid version: %s" % (
                    len(missing), ','.join(missing)
                )
            )
        return self.dependency_solver.explain(catalog)

    @rpc
    @log_all
    def get_latest_phase(self):
        """
        return the latest phase for registered version of all services.
        this don't mean this phase is compatible.
        :return: all service with their latest versions
        :rtype: dict[str, str]
        """
        res = {}
        for service in (self._unserialize_service(serv) for serv in self.mongo.catalog.find()):
            sorted_versions = self.sort_versions(service['versions'].values())
            res[service['name']] = str(sorted_versions[0])
        return res

    @rpc
    @log_all
    def run_available_upgrade(self):
        resolved = self.resolve_upgrade_and_steps()
        """
        result:
            best_phase: Phase
            steps:
                - #Step
        errors:
            step:
            error: $remoteerror
            catalog: $catalog
         """

        result_ = resolved['result']
        if result_ and result_['steps']:
            sched = {
                "state": RUNNING,
                "steps": [
                    {
                        "service": step.service,
                        "from": step.from_,
                        "to": step.to,
                        "state": WAITING

                    }
                    for step in result_['steps']
                ]
            }
            self._run_step(sched['steps'][0], sched)
            # disable all scheduled
            self.mongo.scheduling.update_many({"state": RUNNING}, {"$set": {"state": ABORDED}})
            self.mongo.scheduling.insert_one(sched)
            return filter_dict(sched)
        return None

    @rpc
    @log_all
    def continue_scheduled_plan(self, service, from_version, to_version):
        """
        check if the upgraded service is a part of a active upgrade plan and continue it.
        :param Service service:
        :param str from_version:
        :param str to_version:
        :return:
        """
        running_scheduled = self.mongo.scheduling.find_one({"state": RUNNING})
        if running_scheduled is None:
            # nothing to do since it was not a part of a running upgrade plan
            logger.info("upgrade of service outside of a upgrade plan for %s %s=>%s",
                        service['name'], from_version, to_version)
            return

        updated_step = None
        next_step = None
        for step in running_scheduled['steps']:

            if step['service'] == service['name']:
                # this was our service.
                updated_step = step
            elif step['state'] == DONE:
                continue
            elif step['state'] == WAITING:
                next_step = step
                break

        logger.debug("scheduling: updated_step=%s, next_step=%s", updated_step, next_step)
        if updated_step is None:
            # we did not find the current service in the scheduled plan...
            # this mean our upgrade plan is over and aborded since it's out of sync with upgrade process
            logger.info("abording old scheduling %s", running_scheduled)
            _abord_scheduled(running_scheduled)

        elif next_step is None:
            # the last service was the current one.
            # this upgrade is done
            updated_step['state'] = DONE
            running_scheduled['state'] = DONE
            logger.info("scheduling is finished %s", running_scheduled)
        else:
            # we are still in a upgrade plan
            updated_step['state'] = DONE
            logger.info("scheduling continue with step %s", next_step)
            self._run_step(next_step, running_scheduled)

        self.mongo.scheduling.replace_one({'_id': running_scheduled['_id']}, running_scheduled)

    @rpc
    @log_all
    def resolve_upgrade_and_steps(self):
        """
        resolve the best phase for current catalog and build the steps to got to it.
        this is a dry-run process that will not run any upgrade
        :return: the dict with the result and the errors::

            result:
                best_phase: Phase
                steps:
                 - ($servicename, $from, $to)
            errors:
             step:
             error: $remoteerror
             catalog: $catalog
        """
        catalog = self.build_catalog()
        if self.config.get('solve_dependencies', True):
            # feature realy cpu heavy and algo is O(n**n) :(
            solved_phases = self.dependency_solver.solve_dependencies(catalog)
        else:
            # workaround for hanging resolution
            solved_phases = {
                "results": [self.get_latest_phase()],
                "errors": [],
                "anomalies": []
            }
        """
        phase is the result of a solved state. it contains the list of possible states.
        each states is a list of tuple with a service and his pined version.
        """
        if solved_phases['errors']:
            return {
                "result": None,
                "errors": {
                    "step": "dependency_solve",
                    "error": solved_phases['errors'],
                    "catalog": catalog
                }
            }
        services_by_names = {
            service['name']: service
            for service in catalog
        }

        phases = [
            Phase.deserialize([(services_by_names[k], v) for k, v in phase.items()])
            for phase in solved_phases['results']
        ]
        logger.debug("resolved phases : %s", phases)
        goal, rank = self.solve_best_phase(phases)  # type: Phase[PhasePin], int
        """
        goal is the best noted phase given by all compatible phases.
        """
        if goal is None:
            return {
                "result": {
                    "best_phase": None,
                    "steps": []
                },
                "debug": {
                    "catalog": catalog,
                    "solved_phases": solved_phases,
                    "goal": goal,
                    "rank": rank,
                }
            }
        steps = self.build_steps(goal)
        return {
            "result": {
                "best_phase": goal,
                "steps": steps
            },
            "debug": {
                "catalog": catalog,
                "solved_phases": solved_phases,
                "goal": goal,
                "rank": rank,
            }
        }

    # ################################################
    # private methodes
    # ################################################

    def sort_versions(self, versions):
        """
        short the given version from the hiest version to the lowest
        :param versions: the list of version (as in service['versions']
        :return: a list of version numbers ordered
        """
        sorted_version_metadata = list(sorted(
            versions, reverse=True, key=lambda vinfo: ImageVersion.deserialize(vinfo['image_info'])))
        return [v['version'] for v in sorted_version_metadata]

    def _run_step(self, next_step, running_scheduled):
        # doing the upgrade from to
        service_full_data = self._get_service(next_step['service'])
        if service_full_data is None:
            logger.error("we should upgrade %s %s=>%s but we can't find this service",
                         next_step['service'], next_step['from'], next_step['to'])
            _abord_scheduled(running_scheduled)
        elif next_step['to'] not in service_full_data['versions']:
            logger.error("we should upgrade %s %s=>%s but we can't find this version in the catalog.",
                         next_step['service'], next_step['from'], next_step['to'])
            _abord_scheduled(running_scheduled)
        else:
            # now, we ask overseer to upgrade te given service to the expected version.
            # whene this is done, we will be notified by another overseer.service_updated signal
            next_step['state'] = RUNNING
            logger.debug("ask overseer to switch %s to image : %s",
                         service_full_data['name'],
                         service_full_data['versions'][next_step['to']]['image_info'])
            self.overseer.upgrade_service(service_full_data['name'],
                                          service_full_data['versions'][next_step['to']]['image_info'])

    def build_catalog(self, filter_name=NO_DOWNGRADE):
        """
        read the catalog from mongodb and return the catalog formated to be readable from dependency_solver
        :param str|any filter_name: the name of the filter, or a function to filter catalog versions


        :return: the catalog in the expected form::
            -   name: "myservice"
                versions:
                    $version:
                        provide: {"rpc:holle": 1, "rpc:hello:args": ["name"]}
                        require: ["myservice:rpc:hello", "myservice:rpc:hello>1",
                                  "'name' in myservice:rpc:hello:args"]
        """
        if callable(filter_name):
            filter_func = filter_name
        else:
            filter_func = CATALOG_FILTERS[filter_name]
        res = []
        for service in (self._unserialize_service(s) for s in self.mongo.catalog.find()):
            versions = {}
            res.append({
                "name": service['name'],
                "versions": versions
            })
            for version in service['versions'].values():
                if filter_func(version, service):
                    versions[version['version']] = {
                        "provide": version['dependencies'].get('provide', {}),
                        "require": version['dependencies'].get('require', []),
                    }
            if len(versions) == 0:
                logger.warning("all %d versions was filtered out by filter %s for service %s",
                               len(service['versions']), filter_name, service['name'])
        return res

    def reduce_catalog(self, catalog):
        for service in catalog:
            versions = []
            known_req = []
            for version_number, version_metadata in sorted(service['versions'].items(), key=lambda v: v[0]):
                if version_metadata not in known_req:
                    versions.append((version_number, version_metadata))
                    known_req.append(version_metadata)

            service['versions'] = dict(versions)
        return catalog

    def solve_best_phase(self, phases):
        """
        solve the best phase
        :param list[Phase[PhasePin]] phases: the list of all available phases.
        :return: the phases with most advanced version for most services along with it's score.
        :rtype: tuple[Phase, int]

        the score is a integer between 0 and +inf. the lower the better since 0 mean all newest versions available.
        """
        services = {
            s['name']: [
                iv
                for iv in self.sort_versions(s['versions'].values())
            ]
            for s in (self._unserialize_service(serv) for serv in self.mongo.catalog.find())
        }
        best_phase = None
        best_score = None

        for phase in phases:
            score = 0
            for service, version in phase:
                sorted_version = services[service['name']]

                try:
                    score += sorted_version.index(
                        version
                    )
                except ValueError as ve:
                    logger.exception("%s not in service versions %s %s", version, service['name'], sorted_version)
                    raise
            if best_score is None or best_score > score:
                best_score, best_phase = score, phase

        return best_phase, best_score

    def build_steps(self, goal):
        """
        build the steps to start from current phase and go to «goal» phase.
        each step will upgrade only one service at a time, ensuring that each steps is a
        compatible phase.
        :param Phase[PhasePin] goal: the phase to go to
        :return:
        """
        current_phase = {
            s['name']: s['version']
            for s in self.mongo.catalog.find()
        }
        goal_phase = {p.service['name']: p.version for p in goal}
        if current_phase == goal_phase:
            logger.debug("we already are in the goal phase.")
            return []

        logger.debug("check how to start from %s and finish in %s", current_phase, goal_phase)
        changed_service = []
        for service, version in goal_phase.items():
            if current_phase[service] != version:
                changed_service.append((service, current_phase[service], version))  # service => (from, to)

        def backtrack(steps, fixed_version, rest):
            if not rest:
                return steps

            for service, from_, to_ in rest:
                tested_step = copy.copy(fixed_version)
                tested_step[service] = to_
                logger.debug("try if it's possible : %s" % (tested_step))
                explain_phase = self.explain_phase(tested_step)
                if explain_phase['results'] == 0:  # mean 0 error for this phase
                    solution = backtrack(steps + [Step(service, from_, to_)], tested_step,
                                         [r for r in rest if r[0] != service])
                    if solution is not None:
                        return solution
                else:
                    logger.debug("cant go to %s\n%s", tested_step, explain_phase)

        return backtrack([], current_phase, changed_service)

    def _serialize_service(self, service):
        """
        change data in service to make it compatible for mongodb
        :param service: dict
        :return: dict
        """
        s = filter_dict(service)
        s['versions_list'] = list(s['versions'].values())
        del s['versions']
        return s

    def _unserialize_service(self, service_raw):
        """
        load the data from mongodb and return a python structured service
        :param service_raw:
        :return:
        """
        if service_raw is None:
            return None
        s = deepcopy(service_raw)
        try:
            s['versions'] = {v['version']: v for v in s['versions_list']}
            del s['versions_list']
        except KeyError:
            pass
        return s

    def _get_service(self, service_name):
        """
        load from the database the given service
        :param service_name: the name of the service
        :return:
        """
        return self._unserialize_service(self.mongo.catalog.find_one({'name': service_name}))

    def _save_service(self, service):
        """
        save in the database the given service. replace existing entry if name match.
        :param service: the Service
        :return:
        """
        self.mongo.catalog.replace_one(
            {'name': service['name']},
            self._serialize_service(service),
            upsert=True
        )
