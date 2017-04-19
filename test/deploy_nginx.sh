#!/usr/bin/env bash

docker build -t "nginx:$1" --build-arg text="$1" .
docker tag nginx:"$1" localdocker:5000/nginx:"$1"
docker push localdocker:5000/nginx:$1

