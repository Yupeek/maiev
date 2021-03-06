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
	export RABBITMQ_USER=$(echo -n "RABBITMQ_USER : ">&2; read user; echo $user)
	export RABBITMQ_PASSWORD=$(echo -n "RABBITMQ_PASSWORD : ">&2; read -s password; echo $password)
	export RABBITMQ_HOST=$(echo -n "RABBITMQ_HOST : ">&2; read host; echo $host)

	docker swarm init  --advertise-addr  $MYADDR
	docker network create --driver overlay --subnet 10.0.9.0/24 ${NETWORK_NAME}

mongodb setup
=============

all services which require a mongodb to work will connect to the database given by the env MONGO_URIS.
you will pass this env during the `docker service create` call via the `-e MONGO_URIS="${MONGO_URIS}"` flag.


rabbitmq service
================

the message queue used by maiev is rabbitmq. try to install it on a specific part of your stack (dedicated host).
using a rabbitmq as a swarm service is discouraged.


all in one: global
==================

maiev is split into 7 components built as micro-services. but to be easier to depoly, we made a uniq image named «global»
which ship all 7 services into one docker image. this is the fastest way to deploy maiev.

**this is the recomended deployment process**


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
        --secret source=maiev_docker_cred.json,target=/home/service/.docker/config.json \
        --publish 80:8000 \
        --constraint 'node.role == manager' \
        yupeek/maiev:global-latest

this will start maiev. with the folowing specificites.

- all env RABBITMQ_* will be used to connect to rabbitmq.
- the scaler_docker part will use the "--mount" to connect to the docker swarm cluster and control it. so
  it's required that maiev run in a manager node (as forced by --constraint)
- the scaler_docker may need to connect to private registry or project. so we add a secret with our current docker
  credentials. (docker secret add + --secret source=,target=)
- the scaler docker service should be notified for new images. so his port 8000 must be published. the host port can
  be anything you whant, but must match the webhook you configured in your docker registry.
- the MONGO_URIS should be a full uri to connect to mongodb. keep in mind that there will be many databases created.


detailed services
*****************

each services of maiev is shiped as a dedicated image if you don't use global.
this part of the documentation is not recomanded because of his complexity.


scaler_docker
=============

the service which manage docker. it must be able to acced a manager node by TCP.

tls enabled authentication is a realy good idea. the certificate for authentication should be added as
a swarm secret

with socket mount
-----------------

this is the easiest way to work with a secure stuff. it just require to run scaler-docker on a manager node.

.. code:: bash

	docker service create \
		-d=false \
		--name scaler_docker \
		--network ${NETWORK_NAME} \
		--constraint 'node.role == manager' \
		--mount type=bind,src=//var/run/docker.sock,dst=/var/run/docker.sock \
		-e RABBITMQ_HOST=${RABBITMQ_HOST} \
		-e RABBITMQ_USER=${RABBITMQ_USER} \
		-e RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} \
		-e DOCKER_HOST=unix:///var/run/docker.sock \
		--publish 9007:8000 \
		docker.io/yupeek/maiev:scaler_docker-${MAIEV_VERSION}

with TLS
--------

this setup is secure and don't require to run on a worker. it forbide manipulation of your manager via other service than scaler_docker.
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

docker registry auth
--------------------

to allow access to privates image or registry, you can use docker swarm secrets to pass a specific .docker/config.json file
which will be used to auth against registry. to do this:

- add a secrets to the swarm, containing your config.json [	`cat ~/.docker/config.json | docker secret create mydockerauthsecret.json -` ]
- attache this secret while creating the scaler_config service [ `--secret hashofthesecret` ]
- pass the secret name as an environment variable named DOCKER_CREDENTIALS_SECRET [ `-e DOCKER_CREDENTIALS_SECRET=mydockerauthsecret.json` ]


monitorer rabbitmq
==================

the service that fetch rabbitmq metrics to detect load

.. code:: bash

	docker service create -d=false \
		--name monitorer_rabbitmq \
		--network=${NETWORK_NAME} \
		-e MONGO_URIS="${MONGO_URIS}" \
		-e RABBITMQ_HOST=${RABBITMQ_HOST} \
		-e RABBITMQ_USER=${RABBITMQ_USER} \
		-e RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} \
		yupeek/maiev:monitorer_rabbitmq-${MAIEV_VERSION}


trigger
=======

thes service that compute each metrics from MQ and send the boolean result to overseer

.. code:: bash

	docker service create -d=false \
		--name trigger \
		-e MONGO_URIS="${MONGO_URIS}" \
		--network=${NETWORK_NAME} \
		-e RABBITMQ_HOST=${RABBITMQ_HOST} \
		-e RABBITMQ_USER=${RABBITMQ_USER} \
		-e RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} \
		yupeek/maiev:trigger-${MAIEV_VERSION}

Overseer
========

the real orchestrator service

.. code:: bash

	docker service create -d=false \
		--name overseer \
		--network ${NETWORK_NAME} \
		-e MONGO_URIS="${MONGO_URIS}" \
		-e RABBITMQ_HOST=${RABBITMQ_HOST} \
		-e RABBITMQ_USER=${RABBITMQ_USER} \
		-e RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} \
		yupeek/maiev:overseer-${MAIEV_VERSION}


Docker full integration
***********************

to allow the live update of docker image upon push, your repository must make a notification request to your
scaler-docker service. to allow that, you must

local registry
^^^^^^^^^^^^^^

docker service create -d=false --name registry_docker --publish 9003:5000 yupeek/maiev:registry_docker-1.0.17

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

