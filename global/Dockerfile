FROM monitorer_rabbitmq:global as monitorer_rabbitmq
FROM trigger:global as trigger
FROM overseer:global as overseer
FROM dependency_solver:global as dependency_solver
FROM load_manager:global as load_manager
FROM upgrade_planer:global as upgrade_planer
FROM scaler_docker:global as scaler_docker


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

USER service


COPY ./app /app


COPY --from=monitorer_rabbitmq /app/service /app/service
COPY --from=trigger /app/service /app/service
COPY --from=overseer /app/service /app/service
COPY --from=dependency_solver /app/service /app/service
COPY --from=load_manager /app/service /app/service
COPY --from=upgrade_planer /app/service /app/service
COPY --from=scaler_docker /app/service /app/service

CMD ["nameko", "run", "--config", "config.yaml", \
"service.dependency_solver.dependency_solver:DependencySolver",\
"service.upgrade_planer.upgrade_planer:UpgradePlaner",\
"service.overseer.overseer:Overseer",\
"service.load_manager.load_manager:LoadManager",\
"service.monitorer_rabbitmq.monitorer_rabbitmq:MonitorerRabbitmq",\
"service.trigger.trigger:Trigger",\
"service.scaler_docker.scaler_docker:ScalerDocker"\
]