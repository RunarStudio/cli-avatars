#!/bin/bash
# record.sh <demo|tutorial|changes|walk> <out-root> [take…]: record each take of the video in its own sandboxed run.
# Each take: fresh data dir and fake HOME under <out-root>/<take>, no network (sandbox.sh), private Xvfb.
# REC_APP is the app checkout to record (default: this one).
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "${REC_APP:-$here/../..}" && pwd)
video=$1 root=$2; shift 2
scene="$here/scene_$video.py"
takes=("$@")
[ ${#takes[@]} -eq 0 ] && mapfile -t takes < <(python3 -c "
import sys; sys.path.insert(0, '$here'); import script
import script_1127; rows = dict(demo=script.DEMO, tutorial=script.TUTORIAL, **script_1127.ROWS)
print('\n'.join(t for t, *_ in rows['$video']))")
node_path=$(dirname "$(dirname "$(readlink -f "$(command -v node)")")")/lib/node_modules/@playwright/mcp/node_modules
for take in "${takes[@]}"; do
  work="$root/$take"
  rm -rf -- "$work"
  mkdir -p "$work/home"
  extra=()
  case $take in
    t_start) extra=(REC_MISSING_REPO=1 REC_SETTLE=0.4) ;;
    t_tour) extra=(REC_TOUR=1 REC_SETTLE=2.5) ;;
    t_update) extra=(REC_BOOTCHECK=1) ;;
    t_rooms) extra=(REC_LATE_ROOM=torre-reloj) ;;
    *_first*) extra=(REC_FIRST_RUN=1 REC_SETTLE=0.3) ;;
    a_leftovers) extra=(REC_W=1366 REC_H=768) ;;
  esac
  case $video in  # the English recordings keep every path on screen under /home/you
    changes|walk) extra+=(REC_LANG=en REC_DATA=/home/you/.local/share/cli-avatars) ;;
  esac
  echo "== $take"
  REC_APP="$repo" "$here/sandbox.sh" "$work/home" REC_TAKE="$take" REC_NODE_PATH="$node_path" REC_VO="${REC_VO:-}" REC_WATCHDOG="${REC_WATCHDOG:-600}" \
    PATH="/home/you/bin:$(dirname "$(readlink -f "$(command -v node)")"):/usr/local/bin:/usr/bin:/bin" "${extra[@]}" \
    "$here/inside.sh" "$repo" "$work" "$scene"
  echo "rc=$? $(grep -c . "$work/marks.jsonl" 2>/dev/null) marks"
  grep -h '"mark": "\(error\|missing\)"' "$work/marks.jsonl" 2>/dev/null
done
