#!/usr/bin/env bash

# this script will join or create a swarm based on his tags if the group has the tag AUTO_SWARM=on
#
# it will at boot time
# get all machine of this scaling group
#
# if current machine is the only one in this scaling group:
#   create the swarm
#   publish the token as a tag [DOCKER_TOKEN] in the scaling group (require iam role)
# else
#  join the current swarm with the existing machines
#
#

# at shutdown time. it will:
# if this is the last machin
#   it remove the tag DOCKER_TOKEN
#   leave (delete) the swarm
# else:
#   just leave the swarm

# the best way to have this behavior is to creat a systemd script like the folowing one.
# cat - > /etc/systemd/system/auto_docker_swarm.service <<EOF
#
# [Unit]
# Description=start/create/auto-join a docker swarm
# ConditionPathExists=/opt/auto_docker_swarm.sh
# Requires=docker.service
# After=docker.service
#
#
#
# [Service]
# Type=oneshot
# ExecStart=/opt/auto_docker_swarm.sh up
# ExecStop=/opt/auto_docker_swarm.sh down
#
#
# RemainAfterExit=yes
#
# EOF

###### usefull tags
#
# if the instance is a member of a scalinggroup, the tags of this scaling group will be
# read to check what behavior is needed at boot time.
#
# AUTO_SWARM: if this value is not «on», this script will DO NOTHING
# DOCKER_TOKER: this tag is set at first launche to store the docker swarm join token. if absent, a new swarm will be
#               created
# MANAGER_IP: if this tag exists, the given ip/dns will be used as manager to join an existing cluster.
# 			  if absent, the ip of a manager is taken by picking a machine of the scaling group different than the current one


STATE=$1

CURRENT_INSTANCE_ID=${CURRENT_INSTANCE_ID:-$(curl http://169.254.169.254/latest/meta-data/instance-id -s)}

function get_ip_of_instance {
    I_ID=$1
    aws ec2 describe-instances --instance-ids "$I_ID" | jq -r ".Reservations[0].Instances[0].NetworkInterfaces[0].PrivateIpAddresses[] | select(.Primary==true) | .PrivateIpAddress"
}

function get_scaling_group_of_instance {
	I_ID=$1
    aws autoscaling describe-auto-scaling-groups | jq ".AutoScalingGroups[] | select(.Instances[].InstanceId==\"$I_ID\")"
}

function get_scaling_tag {
	SCALING_GROUP=$1
	TAGNAME=$2
	aws autoscaling  describe-tags --filters "Name=auto-scaling-group,Values=${SCALING_GROUP}" | jq ".Tags[] | select (.Key==\"${TAGNAME}\") | .Value" -r -e
}

SCALING_GROUP_DATA=$(get_scaling_group_of_instance "$CURRENT_INSTANCE_ID" )
SCALING_GROUP_NAME=$(echo "${SCALING_GROUP_DATA}" | jq '.AutoScalingGroupName' -r)


AUTO_SWARM=$(echo "${SCALING_GROUP_DATA}" | jq -r '.Tags[] | select( .Key=="AUTO_SWARM").Value')
if ! [ "${AUTO_SWARM}" = "on" ];
then
	echo "no swarm creation because of tag AUTO_SWARM missing or not equal to 'on'"
	exit 0
fi

if ! MANAGER_IP=$(get_scaling_tag "${SCALING_GROUP_NAME}" "MANAGER_IP");
then
	MANAGER_ID=$(echo ${SCALING_GROUP_DATA} | jq ".Instances | map(select(.InstanceId!=\"${CURRENT_INSTANCE_ID}\")) | .[0].InstanceId" -r)
	MANAGER_IP=$(get_ip_of_instance ${MANAGER_ID})
fi

if [ "${STATE}" != "down" ];
then
	# state is up, we register or create the swarm
	if DOCKER_TOKEN=$(get_scaling_tag "${SCALING_GROUP_NAME}" "DOCKER_TOKEN") ;
	then
		echo "joining swarm at ${MANAGER_IP}:2377 using token ${DOCKER_TOKEN}"
		docker swarm join --token "${DOCKER_TOKEN}" ${MANAGER_IP}:2377
	else
		CURRENT_IP=$(get_ip_of_instance "${CURRENT_INSTANCE_ID}")
		echo "creating swarm on $CURRENT_IP"
		if docker swarm init  --advertise-addr  "$CURRENT_IP";
		then

			DOCKER_TOKEN=$(docker swarm join-token manager -q)
			echo "publishing token to scaling group ${SCALING_GROUP_NAME}: ${DOCKER_TOKEN}"
			aws autoscaling create-or-update-tags --tags \
				"ResourceId=${SCALING_GROUP_NAME},ResourceType=auto-scaling-group,Key=DOCKER_TOKEN,Value=${DOCKER_TOKEN},PropagateAtLaunch=true"
		else
			echo "already a docker swarm node. no prob, we stay as is"
		fi
	fi
else
	INSTANCE_NUM=$(echo ${SCALING_GROUP_DATA} | jq ".Instances | map(select(.InstanceId!=\"${CURRENT_INSTANCE_ID}\")) | length")
	echo "left runnig instance for this scaling group : ${INSTANCE_NUM}"
	if [ "$INSTANCE_NUM" = "0" ];
	then
		# no more instance on this swarm, we remove the token from the TAGS
		echo "no more instance, removing published token for ${SCALING_GROUP_NAME}"
		aws autoscaling delete-tags --tags \
			"ResourceId=${SCALING_GROUP_NAME},ResourceType=auto-scaling-group,Key=DOCKER_TOKEN"
		# we dont leave the swarm, because if we reboot, this swarm wont' be lost,
		# it will republish a token upon start without loosing previous data
	else
		NODEID=$(docker info -f "{{ .Swarm.NodeID }}")
		echo "${NODEID} leaving the swarm"
		docker node demote ${NODEID}
		docker node update --availability drain ${NODEID}
		sleep 1
		docker swarm leave
		while [ "$(docker -H ${MANAGER_IP} --tls  node  ls -f ID=${NODEID} --format '{{ .Status }}')" != "Down" ]
		do
			echo "waiting for manager to be down"
			sleep 1
		done
		docker -H ${MANAGER_IP} --tls  node rm ${NODEID}
	fi
fi
exit 0