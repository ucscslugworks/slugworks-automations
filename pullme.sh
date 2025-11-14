#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

REPO_DIR="/home/chartier/python/slugworks-automations"
LOG_FILE="/home/chartier/python/slugworks-automations/git_pull.log"

cd "$REPO_DIR"
echo "$(date '+%F %T') --- Running git pull in $REPO_DIR" >> "$LOG_FILE"
/usr/bin/git pull >> "$LOG_FILE" 2>&1
