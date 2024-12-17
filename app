#!/bin/bash

pkill gunicorn

cd "$(dirname "$(readlink -f "$0")")"
source venv/bin/activate
authbind gunicorn
