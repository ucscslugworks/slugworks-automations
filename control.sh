#!/bin/bash

# This script will start the control interface/server and the canvas updater
# it should be run as a cron job on startup by the slugworks user

cd /home/slugworks/slugworks-access-cards
git pull

tmux new -ds control
tmux send-keys -t control 'source /home/slugworks/slugworks-access-cards/venv/bin/activate' Enter
tmux send-keys -t control 'python3 /home/slugworks/slugworks-access-cards/control.py' Enter

tmux new -ds canvas
tmux send-keys -t canvas 'source /home/slugworks/slugworks-access-cards/venv/bin/activate' Enter
tmux send-keys -t canvas 'python3 /home/slugworks/slugworks-access-cards/canvas.py' Enter