#!/bin/bash

cd "$(dirname "$(readlink -f "$0")")/../.."

sudo apt install --upgrade python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
sudo pip install -r src/reader/requirements.txt

sudo apt install --upgrade python3-setuptools
pip install --upgrade adafruit-python-shell
wget https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/master/raspi-blinka.py -P /tmp
sudo -E env PATH=$PATH python3 /tmp/raspi-blinka.py

sudo python3 ../test/blinkatest.py
sudo pip install --upgrade adafruit-circuitpython-neopixel
sudo python3 ../test/neopixeltest.py