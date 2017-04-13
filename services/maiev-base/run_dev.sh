#!/usr/bin/env sh

clean_process() {
	echo 'Stopping nemoko and node';
	killall nameko;
	sleep 1;
	killall node;
}
asyncRun() {
    "$@" &
	pid="$!"

    trap "clean_process" SIGINT SIGTERM

    # A signal emitted while waiting will make the wait command return code > 128
    # Let's wrap it in a loop that doesn't end before the process is indeed stopped
    while kill -0 $pid > /dev/null 2>&1; do
        wait
    done
}

npm install --prefix /app_dev supervisor concurrently


asyncRun node /app_dev//node_modules/.bin/concurrently --kill-others-on-fail --color -c "black.bgWhite,cyan,red"   \
		"test ! -f webpack.config.js || ./node_modules/.bin/webpack --watch" \
	 	"/app_dev//node_modules/.bin/supervisor -w . -e py -n exit -x nameko -- run --config config.yaml ${SERVICE_NAME}"
