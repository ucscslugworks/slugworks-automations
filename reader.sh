#!/bin/bash

# This script will start the reader scanner/alarm code
# it should be run as a cron job on startup by the root user

cd /home/slugworks/slugworks-access-cards
git pull

tmux new -ds reader
tmux send-keys -t reader 'sudo source /home/slugworks/slugworks-access-cards/venv/bin/activate' Enter
tmux send-keys -t reader 'sudo python3 /home/slugworks/slugworks-access-cards/reader.py' Enter