
FROM maiev-base:latest


COPY ./app /app

# build part
RUN test ! -f requirements.txt || pip3 install -r requirements.txt

USER service
CMD ["nameko", "run", "--config", "config.yaml", "service.overseer.overseer"]

