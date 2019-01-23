#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import yaml
from IPython import start_ipython
from nameko.cli.main import setup_yaml_parser
from nameko.cli.shell import make_nameko_helper
import sys

from nameko.constants import AMQP_URI_CONFIG_KEY


def main():
    setup_yaml_parser()
    with open("/app/config.yaml") as fle:
        config = yaml.load(fle)
    if len(sys.argv) > 1:
        config[AMQP_URI_CONFIG_KEY] = sys.argv[1]

    ctx = {}
    ctx['n'] = make_nameko_helper(config)
    ctx['maiev'] = ctx['n'].rpc

    start_ipython([], banner1="maiev shell to %s\nuse maiev.service_name.method(args)" % config[AMQP_URI_CONFIG_KEY],
          user_ns=ctx,
    )


if __name__ == '__main__':
    main()