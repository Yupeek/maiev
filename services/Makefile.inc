.PHONY: clean build help update-base-dep
.DEFAULT_GOAL := help
IMAGE_NAME ?= $(shell basename $(CURDIR))
SERVICE_NAME ?= $(IMAGE_NAME)
CURRENT_MAKEFILE := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
DOCKER_REPO ?= docker.exemple.com
GROUPID ?= $(shell id -g)

help:
	@grep -Ph '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean:
	rm -rf node_modules || /bin/true
	rm -f .install-pip || /bin/true
	rm -rf assets/* || /bin/true

# === BUILD / UPDATE  DOCKER IMAGES

build-image:  ## build this image docker
	cp $(CURRENT_MAKEFILE) $(CURDIR)/Makefile.inc.tmp  # copy common Makefile to include it in docker context
	@docker build -t $(IMAGE_NAME) --build-arg USERID=$(shell id -u) --build-arg GROUPID=$(GROUPID) .
	rm $(CURDIR)/Makefile.inc.tmp

# === DEPLOY DOCKER IMAGE

deploy:
	docker tag $(IMAGE_NAME) $(DOCKER_REPO)/$(IMAGE_NAME)
	docker push $(DOCKER_REPO)/$(IMAGE_NAME)

# === BUILD COMMAND INSIDE DOCKER

node_modules: $(wildcard package.json)
	test ! -f package.json || ( npm install && touch node_modules )

install-tools: node_modules .install-pip
	test -d node_modules || npm install supervisor concurrently

.install-pip: $(wildcard requirements.txt)
	test ! -f requirements.txt || pip3 install -r /app/requirements.txt
	touch .install-pip

build-webpack:
	test ! -f webpack.config.js || ./node_modules/.bin/webpack

build: node_modules build-webpack


# === RUN INSIDE DOCKER

print_info:
	@ip addr | grep 'state UP' -A2 | tail -n1 | awk '{print $2}' | cut -f1  -d'/'

dev: print_info install-tools ## target to run inside a docker container to auto reload the sources.
	./run_dev.sh

# === META

all: build