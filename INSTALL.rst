INSTALLATION
############


Maiev use a micro-service architecture to manage other micro-services. this lead to exploding it to many docker images
that will comunicate via rabbitmq.


the minimal setup must be reached to make it possible to deploy other part. this minimal setup is:

.. note::

	each command given is a exemple to run, please refer to the docker documentation if you don't know what it mean.
	the network name is maiev, you would probably create your own network name matching your whole project, since it
	will be used to run the services along with maiev stack

- a docker swarm running and a overlay network

.. code:: bash

	docker swarm init
	docker network create --driver overlay --subnet 10.0.9.0/24 maiev


- a running rabbitmq instance

.. code:: bash

	docker service create --name rabbitmq --replicas 1 --network=maiev rabbitmq


- a running main monitoring instance (Overseer)

.. code:: bash

	docker service create --name overseer --replicas 1 --network=maeiv overseer


- a running docker scaler to interact with docker swarm

.. code:: bash

	docker service create --name scaler_docker --replicas 1 --network=maeiv --env DOCKER_HOST=docker_swarm_node:2375  scaler_docker

.. note::

	the scaler_docker service must have access to the swarm manager node. this lead to a further configuration for the
	manager node by adding ``-H tcp://0.0.0.0:2375 `` to the dockerd arguments

- a running docker repository configured to push to notify scaler-docker

.. code:: bash

	docker service create --name registry_docker --replicas 1 --network=maeiv --publish 5000:5000 registry_docker

.. note::

	the embeding of the repository in the swarm is possible for easy setup, but will be a problem for production.
	the swarm node must access the repository, so the port 5000 is natively published.
	if this repository is not secure, you must start docker with ``--insecure-registry docker_swarm_node:5000`` on all
	docker that will push to it (and then trigger the upgrade in the swarm)

5 minutes setup
***************

to test this arch, there is a fast way to setup Maiev via the embed makefile.

.. note::

	for this setup to work, you must tweak the statup of docker daemon by adding
	``-H tcp://0.0.0.0:2375 --insecure-registry localdocker:5000`` to your docker startup script.

	a working exemple for a debian with systemd can be `/etc/systemd/system/docker.service.d/experimental.conf`::

		[Service]
		ExecStart=
		ExecStart=/usr/bin/dockerd -H fd:// --experimental -H tcp://0.0.0.0:2375 --insecure-registry localdocker:5000

	don't forget to ``sudo systemctl daemon-reload`` and ``sudo systemctl restart docker`` after adding this file.

	the name «localdocker» must resolve to your public ip

.. code:: bash

	docker run -d --name registry -p 5000:5001 registry:2



Docker full integration
***********************

to allow the live update of docker image upon push, your repository must make a notification request to your
scaler-docker service. to allow that, you must

remote registry
^^^^^^^^^^^^^^^

1. publish the port 8000 of your service scaler-docker

.. code:: bash

	docker service update --publish-add xxxx:8000 scaler-docker

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





