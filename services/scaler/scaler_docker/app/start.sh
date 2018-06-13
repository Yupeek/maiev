#!/usr/bin/env sh


# add credentials if given
if [ ! -z "$DOCKER_CREDENTIALS_SECRET" ];
then
	echo "add credentials from secret $DOCKER_CREDENTIALS_SECRET"
	mkdir -p $HOME/.docker || /bin/true
	ln -s "/run/secrets/$DOCKER_CREDENTIALS_SECRET" "$HOME/.docker/config.json"
fi

exec nameko run --config config.yaml service.scaler_docker.scaler_docker:ScalerDocker