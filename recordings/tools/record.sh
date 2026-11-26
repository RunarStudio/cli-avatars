#!/bin/bash
# record.sh <demo|tutorial> <out-root> [take…]: record each take of the video in its own sandboxed run.
# Each take: fresh data dir and fake HOME under <out-root>/<take>, no network (netns.sh), private Xvfb.
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
video=$1 root=$2; shift 2
scene="$here/scene_$video.py"
takes=("$@")
[ ${#takes[@]} -eq 0 ] && mapfile -t takes < <(python3 -c "
import sys; sys.path.insert(0, '$here'); import script
print('\n'.join(t for t, *_ in (script.DEMO if '$video' == 'demo' else script.TUTORIAL)))")
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
  esac
  echo "== $take"
  "$here/netns.sh" "$work/home" REC_TAKE="$take" REC_NODE_PATH="$node_path" REC_VO="${REC_VO:-}" REC_WATCHDOG="${REC_WATCHDOG:-600}" \
    PATH="$work/home/bin:$(dirname "$(command -v node)"):/usr/local/bin:/usr/bin:/bin" "${extra[@]}" \
    "$here/inside.sh" "$repo" "$work" "$scene"
  echo "rc=$? $(grep -c . "$work/marks.jsonl" 2>/dev/null) marks"
  grep -h '"mark": "\(error\|missing\)"' "$work/marks.jsonl" 2>/dev/null
done
