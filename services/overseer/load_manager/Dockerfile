FROM maiev-base:latest
ARG TARGET=test
RUN if [ "$TARGET" = "dev" ]; then \
	npm install --prefix /app_dev supervisor concurrently ;\
	fi

COPY ./app/requirements.txt /app

RUN test ! -f requirements.txt || pip3 install -r requirements.txt

USER service
CMD ["nameko", "run", "--config", "config.yaml", "service.load_manager.load_manager:LoadManager"]


COPY ./app /app
