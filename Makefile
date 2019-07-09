
.DEFAULT_GOAL := all
SUBDIRS := services global
.PHONY: clean $(SUBDIRS)
NETWORK_NAME ?= maiev
LOCAL_IP ?= $(shell ip a s | awk '/inet /{print $$2}' | grep -v 127.0.0.1 | head -n 1 |  cut -d/ -f 1)
DOCKER_REPO ?= $(LOCAL_IP):5000

help:
	@grep -P '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'


build-image: services/maiev-base $(SUBDIRS)  ## build all services

all:   ## build all docker images, tools and etc
	$(MAKE) build-image

build: $(SUBDIRS) ## build all micro-services's docker images.

deploy: $(SUBDIRS)

test: $(SUBDIRS)

$(SUBDIRS):
	    $(MAKE) -C $@ $(MAKECMDGOALS)

clean: $(SUBDIRS)

install:  ## init current docker to swarm for test
	$(MAKE) build
	$(MAKE) deploy
	@echo "initializating swarm with ip $(LOCAL_IP)"

	-docker swarm init --advertise-addr $(LOCAL_IP)  && sleep 1
	-docker network create --driver overlay --subnet 10.0.9.0/24 $(NETWORK_NAME) && sleep 1
	-docker service create --name rabbitmq --replicas 1 --network=$(NETWORK_NAME) rabbitmq  && sleep 4
	-docker service create --name overseer --replicas 1 --network=$(NETWORK_NAME) $(DOCKER_REPO)/overseer  && sleep 1
	-docker service create --name scaler_docker --env DOCKER_HOST=$(LOCAL_IP):2375 \
		--replicas 1 --network=$(NETWORK_NAME) $(DOCKER_REPO)/scaler_docker  && sleep 1
	-docker service create --name registry_docker --publish 5000:5000 \
		--replicas 1 --network=$(NETWORK_NAME) $(DOCKER_REPO)/registry_docker  && sleep 1

update-global-dep:  ## met a jour le scale.json du global a partir de tout les scale.json des services qu'il englobe
	jq -s '.[0] * (.[1:] | {"dependencies": {"provide": (reduce .[] as $$item ({}; . * if $$item.dependencies.provide == null then {} else $$item.dependencies.provide end)), "require": (reduce .[] as $$item ([]; . + $$item.dependencies.require))}})' \
	    global/app/scale.json $(shell find services/ -iname "scale.json") | \
	         tee global/app/scale2.json
	mv global/app/scale2.json global/app/scale.json

dev:
	TARGET=dev $(MAKE) build-image

build-global:
	TARGET=global $(MAKE) build-image
	$(MAKE) -C global build-image