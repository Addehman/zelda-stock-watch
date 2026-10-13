#!/bin/zsh
# Control the Mac watcher background service.
#   ./service.sh status | stop | start | log
L=com.addehman.zelda-watch
P=~/Library/LaunchAgents/$L.plist
case "$1" in
  stop)   launchctl bootout gui/$(id -u)/$L && echo "stopped (stays off until you run: ./service.sh start)"
          launchctl disable gui/$(id -u)/$L ;;
  start)  launchctl enable gui/$(id -u)/$L
          launchctl bootstrap gui/$(id -u) $P 2>/dev/null; launchctl kickstart gui/$(id -u)/$L && echo started ;;
  log)    tail -n 60 -f "$(dirname "$0")/watch.log" ;;
  *)      launchctl print gui/$(id -u)/$L 2>/dev/null | grep -E "state =|pid =|last exit" || echo "not running" ;;
esac
