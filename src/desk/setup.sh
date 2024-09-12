#!/bin/bash

cd "$(dirname "$(readlink -f "$0")")/../.."

sudo apt install --upgrade python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
sudo pip install -r src/desk/requirements.txt
