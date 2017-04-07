
FROM python:3.6-alpine


ENV RABBITMQ_USER guest
ENV  RABBITMQ_PASSWORD guest
ENV RABBITMQ_HOST rabbitmq
WORKDIR /app
ARG USERID=1000
ARG GROUPID=$USERID

RUN addgroup -g $GROUPID service &&  adduser -D -u $USERID -G service service

RUN apk add --no-cache gcc linux-headers musl-dev make curl nodejs

COPY ./requirements.txt /app/
COPY scale_info.sh /usr/bin/scale_info

RUN cd /app; pip3 install -r requirements.txt && rm requirements.txt


COPY . /app
ADD ./Makefile.inc.tmp /Makefile.inc

RUN make build

# cleanup after build
RUN apk del gcc linux-headers curl

USER service
CMD ["nameko", "run", "--config", "config.yaml", "manager_orchestration"]

