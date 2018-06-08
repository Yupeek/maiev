#!/usr/bin/env sh

export PYTHONUNBUFFERED=1

RESTORE=$(echo -en '\033[0m')
RED=$(echo -en '\033[00;31m')
GREEN=$(echo -en '\033[00;32m')
YELLOW=$(echo -en '\033[00;33m')
BLUE=$(echo -en '\033[00;34m')
MAGENTA=$(echo -en '\033[00;35m')
PURPLE=$(echo -en '\033[00;35m')
CYAN=$(echo -en '\033[00;36m')
LIGHTGRAY=$(echo -en '\033[00;37m')
LRED=$(echo -en '\033[01;31m')
LGREEN=$(echo -en '\033[01;32m')
LYELLOW=$(echo -en '\033[01;33m')
LBLUE=$(echo -en '\033[01;34m')
LMAGENTA=$(echo -en '\033[01;35m')
LPURPLE=$(echo -en '\033[01;35m')
LCYAN=$(echo -en '\033[01;36m')
WHITE=$(echo -en '\033[01;37m')

clean_process() {
	echo 'Stopping nemoko and node';
	killall nameko;
	sleep 1;
	killall node;
}
asyncRun() {
	echo -e "${GREEN}=>${RESTORE} ${MAGENTA}$@${RESTORE}"

    "$@" &
	pid="$!"

    trap "clean_process" SIGINT SIGTERM

    # A signal emitted while waiting will make the wait command return code > 128
    # Let's wrap it in a loop that doesn't end before the process is indeed stopped
    while kill -0 $pid > /dev/null 2>&1; do
        wait
    done
}



asyncRun /app_dev/node_modules/.bin/supervisor -w . -k -RV -e py -n exit -x nameko -- run --config config.yaml \
   "service.dependency_solver.dependency_solver:DependencySolver" \
   "service.upgrade_planer.upgrade_planer:UpgradePlaner" \
   "service.overseer.overseer:Overseer" \
   "service.load_manager.load_manager:LoadManager" \
   "service.monitorer_rabbitmq.monitorer_rabbitmq:MonitorerRabbitmq" \
   "service.trigger.trigger:Trigger" \
   "service.scaler_docker.scaler_docker:ScalerDocker"

