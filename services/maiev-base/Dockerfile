
FROM python:3.6-alpine


ENV RABBITMQ_USER guest
ENV  RABBITMQ_PASSWORD guest
ENV RABBITMQ_HOST rabbitmq
ENV PYTHONUNBUFFERED 1
WORKDIR /app
ARG USERID=1000
ARG GROUPID=$USERID



RUN addgroup -g $GROUPID service;  adduser -D -u $USERID -G $(getent group $GROUPID | cut -d: -f1) service
RUN mkdir /app_dev && chown $USERID:$GROUPID /app_dev

RUN apk add --no-cache gcc linux-headers musl-dev nodejs

COPY ./app /app
COPY scale_info.sh /usr/bin/scale_info

RUN cd /app; pip3 install -r requirements.txt && rm requirements.txt
