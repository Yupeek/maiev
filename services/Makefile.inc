
.PHONY: clean build help update-base-dep
.DEFAULT_GOAL := help
DOCKER = docker

# raw values, not expected to be updated
GROUPID ?= $(shell id -g)

SERVICE_NAME ?= $(shell basename $(CURDIR))
IMAGE_NAME ?= maiev
CURRENT_MAKEFILE := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
SCRIPTS_DIR = $(shell dirname ${CURRENT_MAKEFILE})/../scripts/
TEST_CMD ?= /app/test.sh
MAIN_DIR ?= service

# updated values

TARGET ?= test
TEAMCITY_VERSION ?=
DOCKER_REPO ?= yupeek
BUILD_NUMBER ?= dev
SERVICE_FORCE_PUSH ?= \0

# version defining
IMAGE_VERSION ?= latest
FULL_IMAGE_ID ?= $(IMAGE_NAME):$(SERVICE_NAME)-$(IMAGE_VERSION)
TMP_IMAGE_NAME ?= $(SERVICE_NAME):$(TARGET)


# computed values
FLAG_TEAMCITY_VERSION ?= $(shell [ -z "$(TEAMCITY_VERSION)" ] || echo "-e  TEAMCITY_VERSION='$(TEAMCITY_VERSION)'" )

help:
	@grep -Ph '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

clean:
	rm -rf node_modules || /bin/true
	rm -f .install-pip || /bin/true
	rm -rf assets/* || /bin/true

# === BUILD / UPDATE  DOCKER IMAGES

build-image:  ## build this image docker 2
	@test ! -z "$(TARGET)" || (printf "\033[31;1m build image is now specialized.\033[0m\
	 	please set \033[35mTARGET\033[0m env to either \033[36mdev\033[0m, \033[36mprod\033[0m or \033[36mtest\033[0m\n" && /bin/false)

	@test -z "$(TEAMCITY_VERSION)" || echo "##teamcity[blockOpened name='building image $(TMP_IMAGE_NAME)']"
	$(DOCKER) build \
		--build-arg VERSION=$(IMAGE_VERSION) \
		--build-arg TARGET=$(TARGET) \
		--build-arg USERID=$(shell id -u) \
		--build-arg GROUPID=$(GROUPID)\
        $(DOCKER_BUILD_ARGS) \
		-t $(TMP_IMAGE_NAME) \
		.
	@echo built $(TMP_IMAGE_NAME)
	@test -z "$(TEAMCITY_VERSION)" || echo "##teamcity[blockClosed name='building image $(TMP_IMAGE_NAME)']"


# === DEPLOY DOCKER IMAGE

deploy:  ## deploy the image to $DOCKER_REPO with final tag

	@{ \
	push_docker() { \
		test -z "$(TEAMCITY_VERSION)" || echo "##teamcity[blockOpened name='deploing image $(TMP_IMAGE_NAME) as $(DOCKER_REPO)/$(FULL_IMAGE_ID)']"; \
		$(DOCKER) tag $(TMP_IMAGE_NAME)  $(DOCKER_REPO)/$(FULL_IMAGE_ID); \
		$(DOCKER) push $(DOCKER_REPO)/$(FULL_IMAGE_ID); \
		test -z "$(TEAMCITY_VERSION)" || echo "##teamcity[blockClosed name='deploing image $(TMP_IMAGE_NAME) as $(DOCKER_REPO)/$(FULL_IMAGE_ID)']"; \
	}; \
	if case $(SERVICE_NAME) in $(SERVICE_FORCE_PUSH)) ;; *) false;; esac; then \
		echo forcing push; \
		push_docker; \
	else \
		if TAG=$$($(SCRIPTS_DIR)/get_latest_image.sh $(DOCKER_REPO)/$(IMAGE_NAME) $(SERVICE_NAME)); \
		then \
			$(SCRIPTS_DIR)/check_if_uniq.sh $(TMP_IMAGE_NAME) "$$TAG"; \
			if test $$? -eq 1; \
			then \
				echo "new version of $(DOCKER_REPO)/$(IMAGE_NAME):$(SERVICE_NAME). $$TAG is outdated"; \
				push_docker; \
			else \
				echo "$(TMP_IMAGE_NAME) == $$TAG"; \
				echo "image $(DOCKER_REPO)/$(IMAGE_NAME):$(SERVICE_NAME) did not change: wont push"; \
			fi; \
		else \
			echo "no existing image found on hub for $(DOCKER_REPO)/$(IMAGE_NAME):$(SERVICE_NAME)"; \
			push_docker; \
		fi; \
	fi; \
	}


# === TESTING

dev:  ## build images with target dev
	TARGET=dev $(MAKE) build-image

test-flake8: ## Run flake8 tests
	$(DOCKER) run $(DOCKER_TEST_ARGS) -i $(FLAG_TEAMCITY_VERSION) --rm $(TMP_IMAGE_NAME) \
		flake8 $(MAIN_DIR) --max-complexity 10 || /bin/true  # teamcity-messages will send errors

test-isort: ## run isort check
	$(DOCKER) run $(DOCKER_TEST_ARGS) -i $(FLAG_TEAMCITY_VERSION) --rm $(TMP_IMAGE_NAME) \
		isort -rc $(MAIN_DIR)  -c  --diff

test-quality: test-flake8 test-isort

test: build-image test-quality
	$(DOCKER) run \
	    -i $(FLAG_TEAMCITY_VERSION) \
	    $(DOCKER_TEST_ARGS) \
	    --rm \
	    $(TMP_IMAGE_NAME) \
	    $(TEST_CMD)

pre-commit-test:
	$(DOCKER) run $(DOCKER_TEST_ARGS) -i $(FLAG_TEAMCITY_VERSION) -e FORCE_COLOR=true --rm \
		-v $(shell pwd)/app/$(MAIN_DIR)/:/app/$(MAIN_DIR)/ $(TMP_IMAGE_NAME) \
		sh -c "flake8 $(MAIN_DIR) --max-complexity 10 || /bin/true ; isort -rc $(MAIN_DIR)  -c  --diff"

echo-path:
	@echo $(shell realpath --relative-to="$(shell dirname $(CURRENT_MAKEFILE))" .)

# === META

all: build-image

# === BUILD / UPDATE  DOCKER IMAGES

update-base-dep:  ## update the base image hash for the latest local one
	$(eval BASE_IMAGE ?= $(shell sed -n -e 's#^FROM \([^:]*\):\?.*#\1#p' Dockerfile))
	$(eval BASE_HASH ?= $(shell $(DOCKER) images $(BASE_IMAGE) -q --no-trunc | cut -d: -f2))
	sed -e 's/^FROM \([^:]*\):\?.*/FROM \1:$(BASE_HASH)/' -i Dockerfile
