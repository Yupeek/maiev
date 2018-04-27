#!/usr/bin/env bash


d__basic_auth() {
	#
	# read basic auth credentials from `docker login`
	#

	cat ~/.docker/config.json | jq '.auths["'$1'"].auth' -r
}


d__get_auth_header() {
	# return a token valid for the given image
	# ie : d__get_token yupeek/ganymede:latest
	# ie : d__get_token yupeek/ganymede
	# ie : d__get_token docker-registry.gmd-prod.ypk.li/ganymede:latest
	# ie : d__get_token docker-registry.gmd-prod.ypk.li/ganymede

        rel_repository="$1"
        local registry
        local image
        case "${rel_repository}" in
        	*.*/*|*:*/*)
        		# registry with fqdn
        		registry=${rel_repository%%/*}
        		local token=$(d__basic_auth $registry)
        		if [ "$token" = 'null' ];
				then
        			return 1
        		else
					echo "Basic $token"
					return
        		fi
        	;;

        	*)
        		image=${rel_repository%%:*}
        	;;
		esac
		if [[ "$image" != *"/"* ]]; then
				image="library/$image"
		fi

        local T=$(curl -s \
        	-H "Authorization: Basic $(d__basic_auth https://index.docker.io/v1/)" \
         	-H "Accept: application/json" "https://auth.docker.io/token?service=registry.docker.io&scope=repository:$image:pull" | jq .token -r)
        echo "Bearer $T"
}


d__registry__list() {

	# return a list of available tags for the given repository sorted
	# by version number, descending
	#
	# usage: d__registry__list


	local rel_repository=${1}
	[ -z "$rel_repository" ] && return

	local AUTH=$(d__get_auth_header $rel_repository)
	local host

	case "$rel_repository" in
		*.*/*|*:*/*)
			# registry with fqdn
			local image_n_tag=${rel_repository#*/}
			image=${image_n_tag%%:*}
			host=${rel_repository%%/*}
		;;

		*)
			image=${rel_repository%%:*}
			host="index.docker.io"
		;;
	esac
	if [ "$AUTH"  = '' ];
	then
		curl -s -H "Accept: application/json" \
			"https://$host/v2/$image/tags/list"
		# no https
		if [ $? = 35 ]
		then
			curl -s -H "Accept: application/json" \
			"http://$host/v2/$image/tags/list"
		fi
	else
		curl -s -H "Authorization: $AUTH" -H "Accept: application/json" \
				"https://$host/v2/$image/tags/list"
		# no https
		if [ $? = 35 ]
		then
			curl -s -H "Accept: application/json" \
			"http://$host/v2/$image/tags/list"
		fi
	fi
}

d__get_latest() {

	image=$1
	tag=$2
	docker_response=$(d__registry__list ${image})
	if ! echo ${docker_response} | jq '.tags | map(. | select(startswith("'$tag'"))) | reverse |.[0]' -r
	then
		echo "$0 error with response from docker " >&2
		echo "$0 ${docker_response}" >&2
		echo null
		return 1
	fi
	return 0
}


repository=$1  # yupeek/ganymede
remotetag_pattern=$2   # my-micro-service

res=$(d__get_latest "${repository}" "${remotetag_pattern}") && [ 'null' != "$res" ] && echo "${repository}:${res}"


