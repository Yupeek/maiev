.PHONY: clean build help update-base-dep
.DEFAULT_GOAL := help
IMAGE_NAME ?= $(shell basename $(CURDIR))
SERVICE_NAME ?= $(IMAGE_NAME)
CURRENT_MAKEFILE := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
DOCKER_REPO ?= localhost:5000
GROUPID ?= $(shell id -g)
CLEAN_BUILD ?= true

help:
	@grep -Ph '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean:
	rm -rf node_modules || /bin/true
	rm -f .install-pip || /bin/true
	rm -rf assets/* || /bin/true

# === BUILD / UPDATE  DOCKER IMAGES

build-image:  ## build this image docker
	@docker build \
		-t $(IMAGE_NAME) \
		.
# === DEPLOY DOCKER IMAGE

deploy:
	docker tag $(IMAGE_NAME) $(DOCKER_REPO)/$(IMAGE_NAME)
	docker push $(DOCKER_REPO)/$(IMAGE_NAME)

# === META

all: build