maiev
#####

a monitoring cluster that scale inscances up and down based on message queue latency

the main goal of micro-services is scalability, rolling updates and no-downtimes. this software
has for main goal to painlessly update/scale and monitor a cluster of micro-services.


Stable branch

.. image:: https://img.shields.io/travis/Yupeek/maiev/master.svg
    :target: https://travis-ci.org/Yupeek/maiev

Development status

.. image:: https://img.shields.io/travis/Yupeek/maiev/develop.svg
    :target: https://travis-ci.org/Yupeek/maiev


how it work :

1. it monitore the latency of rpc calls for all micro-services
2. if a queue is too low, it scale up the service that consume this queue
3. if a service has a new version, it updrade the running instances of this services.


what it does not do:

1. create/run/delete instance itself, it delegate it to the stack that do it well (docker). instead it ask for more or less instances.
2. guess what to do for a given service itself. all service must give a config concerning his contrains.



this system is based en plugins to monitor images and load. currently, it support docker and rabbitmq.

the plugins that manage the images and the deployment of the services are called `scaler`.

the plugins that monitor the load are called a `monitorer`.

current developement status
===========================

this library is in heavy developement. it's not expected to work without hard work and debugging.

current delevoppement status:

- auto deploy 50%

  - auto update on push: ok
  - parse version and upgrade only: ok
  - dependency requirement: wip
  - helped deployments: no

- monitoring/autoscaling 85%

  - rules parsing: ok
  - services custom rules: ok
  - rabbitmq monitoring: ok
  - scale up/down from rule result: wip

- management 05%

  - rpc call for crud: ok
  - cli for crud: never
  - webui for crud: no
  - live status in webui: no

from now, we can just live upgrade a set of service based on their tags or image name.


docker scaller
==============

the docker scaller use docker swarm to manage the service. in truth, it offload all the work to swarm, just
giving a interface with it to update the running services.


monitor a running image
=======================

to monitor a running image:

create your swarm service with somthing like that

.. code:: bash

	docker service create --name consumer --publish 8084:8000 --network maiev localhost:5000/maiev:consumer-1.0.0


connect to the overseer service in a shell

.. code:: bash

	RABBITMQ_HOST=IP_OF_RABBITMQ nameko shell --config services/maiev-base/app/config.yaml

.. code:: python

	# list current services
	n.rpc.overseer.list_service()
	# add to the monitoring a already created service
	n.rpc.overseer.monitor('docker', 'consumer')

