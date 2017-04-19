
FROM registry:2

ARG SCALER_NAME=scaler-docker
RUN echo $'notifications:\n\
  endpoints:\n\
    - name: docker-scaler\n\
      url: http://scaler_docker:8000/event\n\
      timeout: 250ms\n\
      threshold: 5\n\
      backoff: 10s\n'\
>> /etc/docker/registry/config.yml
