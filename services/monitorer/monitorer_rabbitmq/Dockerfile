FROM maiev-base:latest
ARG TARGET=test
RUN if [ "$TARGET" = "dev" ]; then \
	npm install --prefix /app_dev supervisor concurrently ;\
	fi

USER service
CMD ["nameko", "run", "--config", "config.yaml", "service.monitorer_rabbitmq.monitorer_rabbitmq"]


COPY ./app /app
