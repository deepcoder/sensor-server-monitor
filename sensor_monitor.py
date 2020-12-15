#! /usr/bin/env -S python3 -u
#force unbuffered stdout output for piping to another program
#####! /usr/bin/env python3
#
# sensor_monitor.py
# 202012151112              
#
# check to see if sensors are publishing to MQTT on a periodic basic, if not then alert

#
PROGRAM_NAME = "sensor_monitor"
VERSION_MAJOR = "1"
VERSION_MINOR = "2"
WORKING_DIRECTORY = "/home/user/sensor_monitor/"

# 
# 
#

import sys
import cProfile

# check version of python
if not (sys.version_info.major == 3 and sys.version_info.minor >= 7):
    print("This script requires Python 3.7 or higher!")
    print("You are using Python {}.{}.".format(sys.version_info.major, sys.version_info.minor))
    sys.exit(1)
#print("{} {} is using Python {}.{}.".format(PROGRAM_NAME, PROGRAM_VERSION, sys.version_info.major, sys.version_info.minor))


import json
from urllib import request

import traceback
from pathlib import Path
import yaml
import queue
from dateutil.parser import parse
import paho.mqtt.client as mqtt
import time
from datetime import datetime
from timeloop import Timeloop
from datetime import timedelta
from dateutil import tz
import http.client, urllib
import logging
import logging.handlers
import paramiko

# Logging setup

# select logging level
logging_level_file = logging.getLevelName("DEBUG")
#level_file = logging.getLevelName('DEBUG')
logging_level_rsyslog = logging.getLevelName("INFO")

# set local logging
LOG_FILENAME = PROGRAM_NAME + '.log'

root_logger = logging.getLogger()

#set loggers

# file logger
handler_file = logging.handlers.RotatingFileHandler(WORKING_DIRECTORY + LOG_FILENAME, backupCount=5)
handler_file.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)-8s ' + PROGRAM_NAME + ' ' + '%(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
handler_file.setLevel(logging_level_file)

root_logger.addHandler(handler_file)

# Roll over on application start
handler_file.doRollover()

# configure highest level combo logger, this is what we log to and it automagically goes to the log receivers that we have configured
# logging.getLogger("timeloop").setLevel(logging.CRITICAL)
my_logger = logging.getLogger(PROGRAM_NAME)

# read yaml config file which lists the air purifer units
try :
    raw_yaml = Path(WORKING_DIRECTORY + PROGRAM_NAME + ".yaml").read_text()
except Exception as e:
    my_logger.error("Error : configuration file : " + WORKING_DIRECTORY + PROGRAM_NAME + ".yaml" + " not found.")
    sys.exit(1)

try : 
    PROGRAM_CONFIG = yaml.load(Path(WORKING_DIRECTORY + PROGRAM_NAME + ".yaml").read_text(), Loader=yaml.FullLoader)
except Exception as e :
    my_logger.error("Error : YAML syntax problem in configuration file : " + WORKING_DIRECTORY + PROGRAM_NAME + ".yaml" + " .")
    sys.exit(1)

# read debug from YAML config file
# simple key value pair in YAML file : debug_level: "level" and set debug level
DEBUG_LEVEL = PROGRAM_CONFIG.get("debug_level", "")
if ( DEBUG_LEVEL == "" ) :
    DEBUG_LEVEL = "INFO"

logging_level_file = logging.getLevelName(DEBUG_LEVEL)
handler_file.setLevel(logging_level_file)

# get pushover notification information
PUSHOVER_TOKEN = PROGRAM_CONFIG.get("pushover_token", "")
PUSHOVER_USER = PROGRAM_CONFIG.get("pushover_user", "")
PUSHOVER_ALERT = PROGRAM_CONFIG.get("pushover_sound", "")

# read MQTT server info from YAML config file
# simple key value pair in YAML file : mqtt: "<mqtt server info>"
MQTT_SERVER = PROGRAM_CONFIG.get("mqtt", "")
if ( MQTT_SERVER == "" ) :
    MQTT_SERVER = "192.168.2.242"

# read MQTT server info from YAML config file
# simple key value pair in YAML file : mqtt: "<mqtt server info>"
MQTT_TOPIC_BASE = PROGRAM_CONFIG.get("mqtt_topic", "")

# read rsyslog info from YAML config file
# simple key value pair in YAML file : rsyslog: "<rsyslog server info>"
# simple string
RSYSLOG_SERVER = PROGRAM_CONFIG.get("rsyslog", "")
LOG_RSYSLOG = (RSYSLOG_SERVER, 514)

# rsyslog handler, if an IP address was specified in the YAML config file that configure to log to a RSYSLOG server
if (RSYSLOG_SERVER != "") :
    handler_rsyslog = logging.handlers.SysLogHandler(address = LOG_RSYSLOG)
    handler_rsyslog.setFormatter(logging.Formatter(fmt='%(asctime)s %(levelname)-8s ' + PROGRAM_NAME + ' ' + '%(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    handler_rsyslog.setLevel(logging_level_rsyslog)
    root_logger.addHandler(handler_rsyslog)

logging_level_file = logging.getLevelName('DEBUG')
root_logger.setLevel(logging_level_file)
# how often to check the winix cloud for updated from each unit, be careful to not be to quick at updates
# this is in minutes
CHECK_PERIOD_MINUTES = PROGRAM_CONFIG.get("check_interval", 5)

REBOOT_SERVER = "192.168.88.10"
REBOOT_USER = "pi"
REBOOT_PASSWORD = "raspberry"
REBOOT_COMMAND = "sudo reboot"

# debug, check that the YAML reads and messaging are correct
my_logger.debug("MQTT_SERVER          :" + str(MQTT_SERVER))
my_logger.debug("MQTT_TOPIC_BASE      :" + str(MQTT_TOPIC_BASE))
my_logger.debug("LOG_RSYSLOG          :" + str(LOG_RSYSLOG))
my_logger.debug("CHECK_PERIOD_MINUTES :" + str(CHECK_PERIOD_MINUTES))
my_logger.debug("PUSHOVER_ALERT       :" + str(PUSHOVER_ALERT))

# setup timeloop, this allows to schedule the pull of units current status from winix cloud on regular basis
# https://github.com/sankalpjonn/timeloop
tl = Timeloop()

# create MQTT client globally
# connect to MQTT server
mqttc = mqtt.Client(PROGRAM_NAME)  # Create instance of client with client ID 
mqttc.connect(MQTT_SERVER, 1883)  # Connect to (broker, port, keepalive-time)

# flag to indicate if sensors did update during period
pat_the_watchdog = False
# counter of interval between notifications
alert_number = 0
# flag to check if we rebooted server with sensors
pat_rebooted = False

# functions to handle the command messages from MQTT sources

def message_received(mosq, obj, msg) :
    # we have to check all MQTT messages for either a command to the unit from an MQTT source
    # or a status up MQTT message that was published by this routine (because the current state of a control,
    # might have been change by a interaction with front panel of unit, or command from the mobile phone app)

    global pat_the_watchdog
    
    msg_text = msg.payload.decode("utf-8")

    my_logger.debug("in messages_received, message topic, qos, text: " + msg.topic + " " + str(msg.qos) + " " + msg_text)

    if ( DEBUG_LEVEL == "DEBUG" ) :
        print(".", end="")
    
    # if the message is a status message, aka has subtopic of "$SYS" we can skip
    if ( "$SYS" in msg.topic ) :
        return

    pat_the_watchdog = True
    
    return

# using the timeloop scheduling tool
@tl.job(interval=timedelta(minutes=CHECK_PERIOD_MINUTES))
def periodic_update_units():

    global pat_the_watchdog, alert_number, pat_rebooted

    # if server was rebooted and sensor data now being received, note this
    if (pat_rebooted == True and pat_the_watchdog == True) :
        my_logger.info("server rebooted, sensor updates being received")
        pat_rebooted = False        
        
    # if no update in check period, raise error    
    if (pat_the_watchdog == False) :
        if ( DEBUG_LEVEL == "DEBUG" ) :
            print("!", end="")
        my_logger.error("no update for any bluetooth sensors in check period (minutes) : " + str(CHECK_PERIOD_MINUTES))

        # don't send alert every time
        if (alert_number == 0) :
            # send pushover alert
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request("POST", "/1/messages.json",
              urllib.parse.urlencode({
                "token": PUSHOVER_TOKEN,
                "user": PUSHOVER_USER,
                "sound": PUSHOVER_ALERT,
                "priority": "1",
                "message": "rebooting server, no update for any bluetooth sensors in check period : " + str(CHECK_PERIOD_MINUTES),
              }), { "Content-type": "application/x-www-form-urlencoded" })
            pushover_result = conn.getresponse()
            my_logger.error("notification sent to pushover : " + str(pushover_result.read().decode()))

            # reboot the server
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(REBOOT_SERVER, username=REBOOT_USER, password=REBOOT_PASSWORD, look_for_keys=False, allow_agent=False)
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(REBOOT_COMMAND)
            my_logger.error("server reboot command sent : " + REBOOT_SERVER + " " + str(ssh_stdout) + " " + str(ssh_stderr))
            alert_number = 1
            pat_rebooted = True
        else :
            # increment alert counter and reset if alert period has been run through
            pat_rebooted = False
            alert_number = alert_number + 1
            if (alert_number > 4) :
                alert_number = 0

    else :
        pat_rebooted = False
        if ( DEBUG_LEVEL == "DEBUG" ) :
            print("*", end="")

    # reset the pat, either way
    pat_the_watchdog = False
     
    return

def main():

    # keep track of transition to new day at midnight local time
    # at rollover, reset the tracking of duplicate incident id
    current_day = datetime.now().timetuple().tm_yday

    try :
        # # connect to MQTT server
        # mqttc = mqtt.Client(PROGRAM_NAME)  # Create instance of client with client ID 
        # mqttc.connect(MQTT_SERVER, 1883)  # Connect to (broker, port, keepalive-time)
        # Add message callbacks that will only trigger on a specific subscription match.
        mqttc.message_callback_add(MQTT_TOPIC_BASE + "/" + "#", message_received)
        mqttc.subscribe(MQTT_TOPIC_BASE + "/" + "#", 0)

        my_logger.info("Program start : " + PROGRAM_NAME + " Version : " + VERSION_MAJOR + "." + VERSION_MINOR)

        # Start mqtt
        mqttc.loop_start()

        # start timeloop thread to update units on periodic basis
        tl.start()

        # loop forever waiting for keyboard interrupt, seeing if there are unit update requests queued
        while True :

            # check if it is a new day, if so clear out the record of duplicate incidents published during prior day
            # publish to MQTT a stat about how many unique incidents were published in prior day
            if current_day != datetime.now().timetuple().tm_yday :
                my_logger.info("24 hour rollover")
                current_day = datetime.now().timetuple().tm_yday

            time.sleep(1)
        # end loop forever

    except KeyboardInterrupt :
        tl.stop()
        message = {"timestamp": "{:d}".format(int(datetime.now().timestamp()))}
        message["program_version"] = PROGRAM_NAME + " Version : " + VERSION_MAJOR + "." + VERSION_MINOR
        message["status"] = "STOP"
        mqttc.publish(MQTT_TOPIC_BASE + "$SYS/STATUS", json.dumps(message))
        mqttc.disconnect()
        mqttc.loop_stop()
        my_logger.info("Keyboard interrupt.")
        # sys.exit(0)

    except :
        tl.stop()
        my_logger.critical("Unhandled error : " + traceback.format_exc())
        sys.exit(1)

    # proper exit
    print("")
    print("")
    my_logger.info("Program end : " + PROGRAM_NAME + " Version : " + VERSION_MAJOR + "." + VERSION_MINOR)
    sys.exit(0)

if __name__ == '__main__':
   main()
# if __name__ == '__main__':
#     cProfile.run('main()')
