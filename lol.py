# -*- coding: utf-8 -*-

import logging.config

import yaml
c = yaml.load(open('logcfg.yaml'))

print(c['LOGGING']['formatters']['colored']['format'])

print("\u001B[1;32m%(lineno)s")