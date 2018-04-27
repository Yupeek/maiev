FROM maiev-base:latest
ARG TARGET=test
RUN if [ "$TARGET" = "dev" ]; then \
	npm install --prefix /app_dev supervisor concurrently ;\
	fi

COPY ./app /app

# build part
RUN test ! -f requirements.txt || pip3 install -r requirements.txt


# cleanup after build
RUN apk del gcc linux-headers


USER service
CMD ["nameko", "run", "--config", "config.yaml", "service.trigger.trigger"]

