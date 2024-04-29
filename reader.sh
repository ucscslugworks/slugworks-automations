#!/bin/bash

if [[ "$EUID" != 0 ]]; then
    echo "(1) not root"
    sudo -k # make sure to ask for password on next sudo ✱
    if sudo true; then
        echo "(2) correct password"
    else
        echo "(3) wrong password"
        exit 1
    fi
fi
source /home/slugworks/slugworks-access-cards/venv/bin/activate
sudo python3 /home/slugworks/slugworks-access-cards/reader.py