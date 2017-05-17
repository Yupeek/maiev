
FROM maiev-base:latest

COPY ./app /app

RUN test ! -f requirements.txt || pip3 install -r requirements.txt
# build part

# cleanup after build
RUN apk del gcc linux-headers

RUN ln -s /run/secrets/docker_manager_tls.pem /app/ca.pem && \
	ln -s /run/secrets/docker_manager_tls.pem /app/cert.pem && \
	ln -s /run/secrets/docker_manager_tls.pem /app/key.pem


# add to allow volum for /var/run/docker.sock
ARG GROUPID=1000
RUN echo addgroup -g $GROUPID docker;  adduser service $(getent group $GROUPID | cut -d: -f1)

USER service
CMD ["nameko", "run", "--config", "config.yaml", "service.scaler_docker.scaler_docker"]
