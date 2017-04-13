
include ../Makefile.inc


build-image:  ## build this image docker
	@docker build \
		-t $(IMAGE_NAME) \
		--build-arg USERID=$(shell id -u) \
		--build-arg GROUPID=$(GROUPID) \
		.