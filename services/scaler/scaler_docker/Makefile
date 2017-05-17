GROUPID ?= $(shell getent group docker | cut -d: -f3)

include ../../Makefile.inc


build-image:  ## build this image docker
	docker build \
		-t $(SERVICE_NAME) \
		--build-arg GROUPID=$(GROUPID) \
		.