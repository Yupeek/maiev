#!/usr/bin/env bash

REGISTRY=${REGISTRY:-localdocker:5000}
docker build -t "nginx:$1" --build-arg text="$1" .
docker tag nginx:"$1" $REGISTRY/nginx:"$1"
docker push $REGISTRY/nginx:$1

