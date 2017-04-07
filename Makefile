
.DEFAULT_GOAL := all
SUBDIRS := $(shell find services -not -path "*node_modules*" -and  -name Makefile | xargs "dirname" )
.PHONY: clean $(SUBDIRS)

help:
	@grep -P '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

build-service-images: ## build all services
	$(MAKE) build-image

build-image: $(SUBDIRS)  ## build all services

all:   ## build all docker images, tools and etc
	$(MAKE) build-image

build: $(SUBDIRS) ## build all micro-services's docker images.

deploy: $(SUBDIRS)

$(SUBDIRS):
	    $(MAKE) -C $@ $(MAKECMDGOALS)

clean: $(SUBDIRS)