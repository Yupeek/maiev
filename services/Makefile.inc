.PHONY: clean build help update-base-dep
.DEFAULT_GOAL := help
GROUPID ?= $(shell id -g)
SERVICE_NAME ?= $(shell basename $(CURDIR))
IMAGE_NAME ?= maiev
IMAGE_VERSION ?= latest
TAG_NAME ?= $(SERVICE_NAME)-$(IMAGE_VERSION)
CURRENT_MAKEFILE := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
DOCKER_REPO ?= yupeek


help:
	@grep -Ph '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean:
	rm -rf node_modules || /bin/true
	rm -f .install-pip || /bin/true
	rm -rf assets/* || /bin/true

# === BUILD / UPDATE  DOCKER IMAGES

build-image:  ## build this image docker
	docker build \
		-t $(SERVICE_NAME) \
		.
# === DEPLOY DOCKER IMAGE

deploy:
	docker tag $(SERVICE_NAME) $(DOCKER_REPO)/$(IMAGE_NAME):$(TAG_NAME)
	docker push $(DOCKER_REPO)/$(IMAGE_NAME):$(TAG_NAME)

# === META

all: build-image