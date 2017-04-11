
FROM registry:2

ARG SCALER_NAME=scaler-docker
RUN echo $'notifications:\n\
  endpoints:\n\
    - name: docker-scaler\n\
      url: http://scaler_docker:8000/event\n\
      timeout: 500ms\n\
      threshold: 5\n\
      backoff: 1s\n'\
>> /etc/docker/registry/config.yml
