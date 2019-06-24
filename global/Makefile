GROUPID ?= $(shell getent group docker | cut -d: -f3)
DOCKER_TEST_ARGS = --net="host"

include ../services/Makefile.inc


update-requirements:
	find ../services -iname requirements.txt -print0| xargs -0 awk 'FNR==1{print""}1'  | sort -u > app/requirements.txt