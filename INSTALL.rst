INSTALLATION
############


Maiev use a micro-service architecture to manage other micro-services. this lead to exploding it to many docker images
that will communicate via rabbitmq. this micro-service pattern lead to many way to deploy it, and so the folowing setup
is just a small example of a working setup.


the minimal setup must be reached to make it possible to deploy other part. this minimal setup is:

.. note::

	each command given is a exemple to run, please refer to the docker documentation if you don't know what it mean.
	the network name is maiev, you would probably create your own network name matching your whole project, since it
	will be used to run the services along with maiev stack

- a docker swarm running and a overlay network

- a running rabbitmq instance

- a running mondogb instance

- a running main monitoring instance (Overseer)

- a running docker scaler to interact with docker swarm


.. note::

	the scaler_docker service must have access to the swarm manager node. this lead to a further configuration for the
	manager node by adding ``-H tcp://0.0.0.0:2375 `` to the dockerd arguments

- a running docker repository configured to notify push to scaler-docker

.. code:: bash

	docker service create --name registry_docker --replicas 1 --network=maeiv --publish 5000:5000 registry_docker

.. note::

	the embeding of the repository in the swarm is possible for easy setup, but will be a problem for production.
	the swarm node must access the repository, so the port 5000 is published.
	if this repository is not secure, you must start docker with ``--insecure-registry docker_swarm_node:5000`` on all
	docker that will push to it (and then trigger the upgrade in the swarm)

15 minutes setup
****************

to test this arch, there is a fast way to setup Maiev via the embed makefile.

.. note::

	for this setup to work, you must tweak the statup of docker daemon by adding
	``-H tcp://0.0.0.0:2375 --insecure-registry localdocker:5000`` to your docker startup script.

	a working exemple for a debian with systemd can be `/etc/systemd/system/docker.service.d/experimental.conf`::

		[Service]
		ExecStart=
		ExecStart=/usr/bin/dockerd -H fd:// -H tcp://0.0.0.0:2375 --insecure-registry localdocker:5000

	don't forget to ``sudo systemctl daemon-reload`` and ``sudo systemctl restart docker`` after adding this file.

	the name «localdocker» must resolve to your public ip

	.. code:: bash

		echo "$(ip a s | awk '/inet /{print $2}' | grep -v 127.0.0.1 | head -n 1 |  cut -d/ -f 1) localdocker" >> /etc/hosts


create all service for required parts

swarm creation + overlay network
================================

each services need a overlay network to comunicate

.. code:: bash

	export MYADDR="$(ip a s | awk '/inet /{print $2}' | grep -v 127.0.0.1 | head -n 1 |  cut -d/ -f 1)"
	export MONGO_URIS="IP_OR_NAME"
	export NETWORK_NAME=maiev
	export MAIEV_VERSION=latest

	docker swarm init  --advertise-addr  $MYADDR
	docker network create --driver overlay --subnet 10.0.9.0/24 ${NETWORK_NAME}

mongodb setup
=============

all services which require a mongodb to work will connect to the database given by the env MONGO_URIS.
you will pass this env during the `docker service create` call via the `-e MONGO_URIS="${MONGO_URIS}"` flag.


rabbitmq service
================

the message queue used by maiev is rabbitmq

.. code:: bash

	docker service create --name rabbitmq --replicas 1 --network=${NETWORK_NAME} rabbitmq:3-management

scaler_docker
=============

the service which manage docker. it must be able to acced a manager node by TCP.

tls enabled authentication is a realy good idea. the certificate for authentication should be added as
a swarm secret

with TLS
--------

this setup is the most secure. it forbide manipulation of your manager via other service than scaler_docker.
to achieve this, we use a client/server tls certificate verification. if your docker daemon is started with the configuration
using tls, the setup is a folow:

- you have an CA
- you have isued a certificate for your scaler docker using this CA
- you have isued a certificate for your daemon using the same CA
- you have started your daemon with `--tlsverify --tlscacert=/etc/ssl/certs/CA.pem --tlscert=/etc/ssl/certs/dockerdaemon.pem --tlskey=/etc/ssl/private/dockerdaemon.key`

the next setup use the certificate and the key isued for your scaler docker. it need the CA certificate too.

we use this cert.pem (certificate), key.pem (private key) and ca.pem (the CA cert) to create a docker secert shared with
the running scaler docker. this docker will use it to authenticate with the docker daemon.

.. note::

	the name of the secret must be «docker_manager_tls.pem». this is hardcoded into the scaler_docker image


.. code:: bash

	cat cert.pem key.pem ca.pem | docker secret create docker_manager_tls.pem -
	docker service create --name scaler_docker --network maeiv --secret docker_manager_tls.pem -e DOCKER_HOST=tcp://docker_swarm_node:2375 -e DOCKER_TLS_VERIFY=1 -e DOCKER_CERT_PATH=/app docker.io/yupeek/maiev:scaler_docker-${MAIEV_VERSION}

without TLS
-----------

without tls, INSECURE

.. code:: bash

	docker service create --name scaler_docker --network maeiv -e DOCKER_HOST=tcp://docker_swarm_node:2375  docker.io/yupeek/maiev:scaler_docker-${MAIEV_VERSION}

monitorer rabbitmq
==================

the service that fetch rabbitmq metrics to detect load

.. code:: bash

	docker service create --name monitorer_rabbitmq --network=${NETWORK_NAME} -e MONGO_URIS="${MONGO_URIS}" yupeek/maiev:monitorer_rabbitmq-${MAIEV_VERSION}

trigger
=======

thes service that compute each metrics from MQ and send the boolean result to overseer

.. code:: bash

	docker service create --name trigger -e MONGO_URIS="${MONGO_URIS}" --network=${NETWORK_NAME} yupeek/maiev:trigger-${MAIEV_VERSION}

Overseer
========

the real orchestrator service

.. code:: bash

	docker service create --name overseer -e MONGO_URIS="${MONGO_URIS}" --network ${NETWORK_NAME} yupeek/maiev:overseer-${MAIEV_VERSION}


Docker full integration
***********************

to allow the live update of docker image upon push, your repository must make a notification request to your
scaler-docker service. to allow that, you must

remote registry
^^^^^^^^^^^^^^^

1. publish the port 8000 of your service scaler-docker

.. code:: bash

	docker service update --publish-add xxxx:8000 scaler_docker

2. configure your repository to add this url into notifications.
   with scaler-docker a valid dns name resolving to your cluster.

/etc/docker/registry/config.yml::

	...
	notifications:
	  endpoints:
	    - name: docker-scaler
	  	  url: https://scaler-docker:xxxx/event
	  	  timeout: 500ms
	  	  threshold: 5
	  	  backoff: 1s

dedicated registry
^^^^^^^^^^^^^^^^^^

for a dedicated registry, you can use the embded Dockerfile that add a notification push to the scaler-docker host

.. code:: bash

	docker build -f services/scaler/scaler_docker/registry_docer/Dockerfile
	docker service create





