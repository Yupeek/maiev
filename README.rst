maiev
#####

a monitoring cluster that scale inscances up and down based on message queue latency

the main goal of micro-services is scalability, rolling updates and no-downtimes. this software
has for main goal to painlessly update/scale and monitor a cluster of micro-services.

how it work :

1. it monitore the latency of rpc calls for all micro-services
2. if a queue is too low, it scale up the service that consume this queue
3. if a service has a new version, it updrade the running instances of this services.


what it does not do:

1. create/run/delete instance itself, it delegate it to the stack that do it well (docker). instead it ask for more or less instances.
2. guess what to do for a given service itself. all service must give a config concerning his contrains.



