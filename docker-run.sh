#!/usr/bin/env bash 
#
# docker-run.sh
# 202012151341   
#
# http://redsymbol.net/articles/unofficial-bash-strict-mode/
# Unofficial Bash Strict Mode (Unless You Looove Debugging)
set -euo pipefail

docker run -i -t -d --init --name="sensor_monitor" \
    -v /home/user/sensor_monitor:/home/user/sensor_monitor \
    -v /etc/localtime:/etc/localtime:ro \
    --net=host \
    --user $(id -u):$(id -g) \
    sensor_monitor
    