#!/bin/bash
# inside.sh <repo> <work> <scene.py>: (inside netns.sh) a private Xvfb at 1920x1080, then the app with the scene.
set -u
repo=$1 work=$2 scene=$3
mkdir -p "$HOME/tmp" "$work"
disp=:$((90 + RANDOM % 9))
Xvfb "$disp" -screen 0 1920x1080x24 -nolisten tcp -ac >"$work/xvfb.log" 2>&1 &
xpid=$!
export DISPLAY=$disp
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done
xsetroot -cursor_name left_ptr
xdotool mousemove 1900 1062  # park the pointer off the map: one resting on a door plaque froze the Dungeon
python3 "$(dirname "$0")/stage.py" "$repo" "$work" "$scene" >"$work/app.log" 2>&1
rc=$?
kill $xpid 2>/dev/null; wait $xpid 2>/dev/null
exit $rc
