#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import traceback

import yaml
from IPython import start_ipython
from traitlets.config import get_config
from nameko.cli.main import setup_yaml_parser
from nameko.cli.shell import make_nameko_helper
import sys

from nameko.constants import AMQP_URI_CONFIG_KEY


def main():
    setup_yaml_parser()
    with open("/app/config.yaml") as fle:
        config = yaml.unsafe_load(fle)
    if len(sys.argv) > 1:
        config[AMQP_URI_CONFIG_KEY] = sys.argv[1]

    try:
        ctx = {}
        ctx['n'] = make_nameko_helper(config)
        ctx['maiev'] = ctx['n'].rpc

        c = get_config()
        c.IPCompleter.debug = True
        c.IPCompleter.use_jedi = False
        start_ipython(
            [],
            banner1="maiev shell to %s\nuse maiev.service_name.method(args)" % config[AMQP_URI_CONFIG_KEY],
            user_ns=ctx,
            config=c,
        )
    except Exception:
        traceback.print_exc()
        print("failed to start shell to %s" % config[AMQP_URI_CONFIG_KEY])


if __name__ == '__main__':
    main()