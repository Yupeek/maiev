TOPTARGETS := build-image deploy test pre-commit-test dev

SERVICES := $(wildcard */)

$(TOPTARGETS): $(SERVICES)
$(SERVICES):
	    $(MAKE) -C $@ $(MAKECMDGOALS)

.PHONY: $(TOPTARGETS) $(SERVICES)