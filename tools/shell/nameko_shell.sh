#!/bin/sh

if test -z "$1"; then
  nameko shell --config config.yaml
else
  echo "connecting to $1"
  AMQP_URI=$1 nameko shell --config config.yaml
fi
