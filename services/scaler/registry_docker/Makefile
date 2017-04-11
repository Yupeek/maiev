GROUPID ?= $(shell getent group docker | cut -d: -f3)

include ../../Makefile.inc


build-image:  ## build this image docker
	cp $(CURRENT_MAKEFILE) $(CURDIR)/Makefile.inc.tmp  # copy common Makefile to include it in docker context
	@docker build \
		-t $(IMAGE_NAME) \
		.
	rm $(CURDIR)/Makefile.inc.tmp