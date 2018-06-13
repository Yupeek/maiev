GROUPID ?= $(shell getent group docker | cut -d: -f3)
DOCKER_TEST_ARGS = --net="host"
IMAGE_VERSION ?= $(shell cat version).$(TRAVIS_BUILD_NUMBER)


include ../services/Makefile.inc

