#!/bin/zsh
# Keeps the Mac awake (not the display) while the watcher runs.
cd "$(dirname "$0")"
exec caffeinate -i .venv/bin/python watch.py "$@"
