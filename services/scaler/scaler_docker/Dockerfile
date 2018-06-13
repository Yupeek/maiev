
FROM maiev-base:latest

ARG TARGET=test
RUN if [ "$TARGET" = "dev" ]; then \
	npm install --prefix /app_dev supervisor concurrently ;\
	fi

COPY ./app/requirements.txt /app

RUN test ! -f requirements.txt || pip3 install -r requirements.txt

RUN ln -s /run/secrets/docker_manager_tls.pem /app/ca.pem && \
	ln -s /run/secrets/docker_manager_tls.pem /app/cert.pem && \
	ln -s /run/secrets/docker_manager_tls.pem /app/key.pem


# add to allow volum for /var/run/docker.sock
ARG GROUPID=1000
RUN echo addgroup -g $GROUPID docker;  adduser service $(getent group $GROUPID | cut -d: -f1)
COPY ./app /app
USER service
CMD ["/app/start.sh"]
