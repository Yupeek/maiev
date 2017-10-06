#!/bin/bash
#
# this fix the lack of route53 ability to target a scaling group machines
#
# if a scaling group have a tag named AUTO_DNS: each time an instance is launched in this scaling group, if it
# run this script, it will update the given dns name to target all instance of the scaling group.
#
# ie:
# 1. the scaling group has the tag: AUTO_DNS=worker-staging.mycompany.lan
# 2. the image used for this scaling group has:
#
#   - the script in /root/update_dns.sh
#   - the file /etc/cloud/cloud.cfg.d/update_dns.cfg::
#
# 		runcmd:
#  		- [ /root/update_dns.sh ]
#
# each time the group scale, the route 53 with the zone `mycompany.lan.` will have a record `worker-staging.mycompany.lan`
# created/updated with all instance ips
#
# to support removing this instance at shutdown, you must execute this script at shutdown with the arg "down"
# ie : /opt/update_dns.sh down

# a small systemd script can work for up/down feature

#   [Unit]
#   Description=update dns at startup
#   ConditionPathExists=/opt/update_dns.sh
#
#
#   [Service]
#   Type=oneshot
#   ExecStart=/opt/update_dns.sh up
#   ExecStop=/opt/update_dns.sh down
#   RemainAfterExit=yes
#
#
#   [Install]
#   WantedBy=multi-user.target
#

STATE=$1

CURRENT_INSTANCE_ID=${CURRENT_INSTANCE_ID:-$(curl http://169.254.169.254/latest/meta-data/instance-id -s)}

function get_ip_of_instance {
    I_ID=$1
    aws ec2 describe-instances --instance-ids "$I_ID" | jq -r -e ".Reservations[0].Instances[0].NetworkInterfaces[0].PrivateIpAddresses[] | select(.Primary==true) | .PrivateIpAddress"
}

function get_scaling_group_of_instance {
	I_ID=$1
    aws autoscaling describe-auto-scaling-groups | jq -e ".AutoScalingGroups[] | select(.Instances[].InstanceId==\"$I_ID\")"
}


if SCALING_GROUP_DATA=$(get_scaling_group_of_instance "$CURRENT_INSTANCE_ID" );
then
	AUTO_DNS=$(echo "$SCALING_GROUP_DATA" | jq -r '.Tags[] | select( .Key=="AUTO_DNS").Value')
else
	AUTO_DNS=$(aws ec2 describe-instances --instance-ids "$CURRENT_INSTANCE_ID" | jq -e -r ".Reservations[0].Instances[0].Tags[] | select (.Key ==\"AUTO_DNS\") | .Value")
fi
echo "$CURRENT_INSTANCE_ID is in AUTO_DNS: $AUTO_DNS"
[ -z "$AUTO_DNS" ] && exit 1


DOMAIN_NAME=$(echo "$AUTO_DNS" | sed 's/.*\.\([^.]\+\.[^.]\+\)$/\1./')
HOSTED_ZONE=$(aws route53 list-hosted-zones | jq -r ".HostedZones | .[] | select(.Name | contains(\"ypk.lan.\")).Id")
# build the payload of the query from the existing record

PAYLOAD=$(\
        aws route53 list-resource-record-sets --hosted-zone-id "$HOSTED_ZONE" | \
        jq "{\"Comment\": \"add scaling instances group to specified AUTO_DNS\", \"Changes\": [{Action: \"UPSERT\", ResourceRecordSet: .ResourceRecordSets[] | select(.Name== \"$AUTO_DNS.\")}]} "\
)
if [ $(echo "$PAYLOAD" | jq ".Changes | length") = 0 ]; then
    # there is no recordset for this name, we create a new one
    PAYLOAD=$(echo [] | jq "{\"Comment\": \"add scaling instances group to specified AUTO_DNS\", \"Changes\": [{Action: \"UPSERT\", ResourceRecordSet: {Name: \"$AUTO_DNS.\", Type: \"A\",ResourceRecords: [], TTL: 300}}]}")
fi
PAYLOAD_FOR_REMOVE=${PAYLOAD}
# reset all ip of the record
PAYLOAD=$(echo "$PAYLOAD" | jq '.Changes[0].ResourceRecordSet.ResourceRecords =  []')
if [ -z "$SCALING_GROUP_DATA" ];
then
	# not in scaling group data, we set us into this ns
	IP=$(get_ip_of_instance "$CURRENT_INSTANCE_ID")
	echo "add ip $IP"
	PAYLOAD=$(echo "$PAYLOAD" | jq ".Changes[0].ResourceRecordSet.ResourceRecords[.Changes[0].ResourceRecordSet.ResourceRecords | length] |= . + {Value: \"$IP\"}")
else
	for instance_id in $(echo "$SCALING_GROUP_DATA" | jq -c -r ".Instances[] | select(.HealthStatus==\"Healthy\") | .InstanceId");
	do

			# if we are shuting down, we remove our instance from this ns
			if [ "$STATE" != "down" ] || [ "$CURRENT_INSTANCE_ID" != "$instance_id" ]
			then
				# for each instances, add his ip to the payload
				IP=$(get_ip_of_instance "$instance_id")
				echo "add ip $IP"
				PAYLOAD=$(echo "$PAYLOAD" | jq ".Changes[0].ResourceRecordSet.ResourceRecords[.Changes[0].ResourceRecordSet.ResourceRecords | length] |= . + {Value: \"$IP\"}")
			fi
	done;
fi
# if after all add, there is no record, we remove the entry
if [ $(echo "$PAYLOAD" | jq ".Changes[0].ResourceRecordSet.ResourceRecords | length") = 0 ]; then
    # there is no recordset for this name, we create a new one
	PAYLOAD=$(echo "$PAYLOAD_FOR_REMOVE" | jq '.Changes[0].Action =  "DELETE"' )
fi


echo "adding $AUTO_DNS using hosted zone $DOMAIN_NAME ($HOSTED_ZONE)"
echo "$PAYLOAD" | jq .

aws route53 change-resource-record-sets --hosted-zone-id ${HOSTED_ZONE} --change-batch file://<(echo "$PAYLOAD")
