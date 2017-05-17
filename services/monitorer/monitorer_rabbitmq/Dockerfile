
FROM maiev-base:latest


COPY ./app /app

# build part
RUN test ! -f requirements.txt || pip3 install -r requirements.txt


# cleanup after build
RUN apk del gcc linux-headers


USER service
CMD ["nameko", "run", "--config", "config.yaml", "service.monitorer_rabbitmq.monitorer_rabbitmq"]

