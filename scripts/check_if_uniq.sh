#!/usr/bin/env bash
# check if a local image is the same as the remote one
# usage my-microservice:build-17 yupeek/repository:my-microservice-v1
# exit status:
# - 0 imageis same as local => safe to push but useless
# - 1 image exists on repo and don't contains same stuff => push will replace it
# - 2 image don't exists => safe to push too

localtag=$1
remotetag=$2

if docker pull "$remotetag" > /dev/null;
then
	# remote tag exists
	echo "compare ${localtag}  with ${remotetag}"
	if [ "$(docker image inspect ${localtag} | jq '.[0].RootFS')" = "$(docker image inspect ${remotetag} | jq '.[0].RootFS' )" ];
	then
		echo "same image exists on docker hub" > /dev/stderr
		exit 0
	else
		# same images. no diff
		echo "image differ" > /dev/stderr
		exit 1

	fi
else
	echo "image don't exists remotly"
	exit 2
fi

