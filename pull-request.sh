#!/bin/bash

# Stop the original Python code
pkill -f control.py

# Run another set of Python code
echo "update=not-completed" > file.txt
python3 another_code.py

python3 pullcode.py


# Wait until "update=completed"
while [[ "$(cat file.txt)" != "update=completed" ]]; do
    sleep 1
done
if [[ "$(cat file.txt)" == "update=completed" ]]; then
    echo "Update completed"
    rm file.txt
    python3 control.py &
fi
# Start the original Python code again
