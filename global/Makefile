GROUPID ?= $(shell getent group docker | cut -d: -f3)
DOCKER_TEST_ARGS = --net="host"

include ../services/Makefile.inc

