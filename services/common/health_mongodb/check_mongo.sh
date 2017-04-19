#!/usr/bin/env bash

[ "$(echo 'db.stats().ok' | mongo ${MONGO_HOST:-localhost}:27017 --quiet)" = "1" ] || exit 1
