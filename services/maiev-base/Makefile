SERVICE_NAME ?= $(shell basename $(CURDIR))
IMAGE_VERSION ?= $(shell cat version).$(BUILD_NUMBER)
TEST_CMD ?= py.test common --cov=common
MAIN_DIR ?= common



include ../Makefile.inc
