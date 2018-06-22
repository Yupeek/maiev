maiev
#####

a monitoring cluster that scale inscances up and down based on message queue latency

the main goal of micro-services is scalability, rolling updates and no-downtimes. this software
has for main goal to painlessly update/scale and monitor a cluster of micro-services.


Stable branch

.. image:: https://travis-ci.org/Yupeek/maiev.svg?branch=master
    :target: https://travis-ci.org/Yupeek/maiev

Development status

.. image:: https://img.shields.io/travis/Yupeek/maiev/develop.svg
    :target: https://travis-ci.org/Yupeek/maiev


how it work :

1. it monitore the latency of rpc calls for all micro-services
2. if a queue is too low, it scale up the service that consume this queue
3. if a service has a new version, it upgrade the monitored service if possible.


what it does not do:

1. create/run/delete instance itself, it delegate it to the stack that do it well (docker). instead it ask for more or less instances.
2. guess what to do for a given service itself. all service must give a config concerning his constraints



current developement status
===========================

this library is in heavy developement. it's not expected to work without hard work and debugging.

current delevoppement status:

- auto deploy 80%

  - auto update on push: ok
  - parse version and upgrade only: ok
  - dependency requirement: ok
  - helped deployments: no

- monitoring/autoscaling 100%

  - rules parsing: ok
  - services custom rules: ok
  - rabbitmq monitoring: ok
  - scale up/down from rule result: ok

- management 05%

  - rpc call for crud: ok
  - cli for crud: never
  - webui for crud: no
  - live status in webui: no


run it now
==========

with a docker swarm setup, you can do this:

.. code-block:: bash

    MAIEVPASSWD='mycommonpassword'
    # docker login to access private repository
    cat ~/.docker/config.json | docker secret create maiev_docker_cred.json -

    docker service create \
        --name maiev \
        --mount type=bind,src=//var/run/docker.sock,dst=/var/run/docker.sock \
        -e RABBITMQ_HOST=rabbitmq.myservices.com \
        -e RABBITMQ_VHOST=/maiev \
        -e RABBITMQ_USER=maiev \
        -e RABBITMQ_PASSWORD=$MAIEVPASSWD \
        -e MONGO_URIS=mongodb://maive:$MAIEVPASSWD@mongodb.myservices.com/overseer \
        --secret maiev_docker_cred.json \
        -e DOCKER_CREDENTIALS_SECRET=maiev_docker_cred.json \
        --publish 80:8000 \
        --constraint 'node.role == manager' \
        yupeek/maiev:global-latest

this will start maiev. it will query all existings services to start monitoring each one which has the
command «scaler_info».