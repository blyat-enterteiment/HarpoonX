#!/bin/sh
set -eu
while true; do
 python /app/backup.py
 sleep 21600
done
