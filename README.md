# sensor-server-monitor
Python program to check if sensor data is being received in MQTT, if not send PushOver alert and reboot the server doing MQTT publishing.

target server IP address, user and password are currently hard coded in application, see these variables in code:

```
REBOOT_SERVER = "192.168.1.42"
REBOOT_USER = "pi"
REBOOT_PASSWORD = "raspberry"
REBOOT_COMMAND = "sudo reboot"
```

The MQTT server IP address and MQTT topic are stored in a .yaml file. Also the login info for 'pushover' notification service is stored here as well. If you do not have a rsyslog server, you can either set a blank IP address, or just leave, the program will write local log files, either way.

The BLE c program to receive the BLE advertising packets from the temperature sensors has been pretty reliable, however there are events that seem to make the bluetooth stack burp. And the c program does not recover. So this Python 3 program monitors the output of that c program to MQTT. If no MQTT data is received from any of the sensors under the MQTT topic, then action is taken.

Note, the program runs outside the Docker container on the host machine.

The program has a configuration file of same name with .yaml extension

# docker build and run

```
/home/user/sensor_monitor

docker build . -t sensor_monitor

./docker-run.sh

```
