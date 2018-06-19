# -*- coding: utf-8 -*-
import json
import logging
import sys

from booleano.exc import ScopeError

from service.dependency_solver.dependency_solver import Solver

logger = logging.getLogger(__name__)


def get_formated_input():
    input_ = json.load(sys.stdin)

    if isinstance(input_, dict):
        for k, v in input_.values():
            v['name'] = k
    elif not isinstance(input_, list):
        raise Exception("input_ should be a list of scale.json")
    return input_


def explain_stdin():
    input_ = get_formated_input()
    catalog = []
    for i, scale_cfg in enumerate(input_):
        if scale_cfg is None:
            continue
        provide = scale_cfg.get("dependencies", {}).get('provide', {})
        require = scale_cfg.get("dependencies", {}).get('require', [])
        name = scale_cfg.get('name')
        if not name:
            try:

                name = list(provide)[0].split(':')[0]
            except (IndexError, TypeError, KeyError) as e:
                name = chr(65 + i)

        catalog.append({
            "name": name,
            "versions": {
                "dev": {
                    "provide": provide,
                    "require": require
                }
            }
        })

    if not catalog:
        raise Exception('bad formated catalog')

    s = Solver(catalog, (), debug=True)
    try:
        return {
            "fail_count": s.explain(),
            "errors": [],
            "anomalies": s.anomalies,
            "failed": s.failed
        }
    except ScopeError as e:
        logger.exception("scope error")
        return {
            "fail_count": None,
            "anomalies": s.anomalies,
            "failed": s.failed,
            "errors": [
                {"type": "missing scope",
                 "str": str(e)
                 }
            ]
        }


if __name__ == '__main__':
    expl = explain_stdin()
    print(json.dumps(expl))
    sys.exit(0 if expl['fail_count'] == 0 else 1)
