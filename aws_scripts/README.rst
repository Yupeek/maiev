amazon EC2 script
#################


this is a set of small script that help for amazon deployment.



update_dns.sh
+++++++++++++

this fix the lack of route53 ability to target a scaling group machines

if a scaling group have a tag named AUTO_DNS: each time an instance is launched in this scaling group, if it
run this script, it will update the given dns name to target all instance of the scaling group.

ie:
1. the scaling group has the tag: AUTO_DNS=worker-staging.mycompany.lan
2. the image used for this scaling group has:

  - the script in /root/update_dns.sh
  - the file /etc/cloud/cloud.cfg.d/update_dns.cfg::

		runcmd:
 		- [ /root/update_dns.sh ]

each time the group scale, the route 53 with the zone `mycompany.lan.` will have a record `worker-staging.mycompany.lan`
created/updated with all instance ips


auto_docker_swarm.sh
++++++++++++++++++++

this script allow to auto-join a cluster at boot, and auto leave the cluster at shutdown for ec2 instances.

if the instance is in a scaling group and this saling group has a tag AUTO_SWARM=on, il will create the swarm
or join other instances.


it require :

- the image to run this script at boot time and shutdown time (see systemd script in comments)
- the role of the instance allowed to get autoscaling info
