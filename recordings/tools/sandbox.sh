#!/bin/bash
# sandbox.sh <home> <cmd…>: run cmd in bwrap with loopback only (no route out), the real /home hidden and <home>
# mounted as /home/you; the app checkout ($REC_APP), these tools and node stay readable. Clean env.
home=$1; shift
here=$(cd "$(dirname "$0")" && pwd)
node_root=$(dirname "$(dirname "$(readlink -f "$(command -v node)")")")
args=(--dev-bind / / --tmpfs /home --bind "$home" /home/you --unshare-net --die-with-parent)
pw=${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}  # its ffmpeg records the phone page
for keep in "${REC_APP:?}" "$here" "$node_root" "$pw"; do args+=(--ro-bind "$keep" "$keep"); done
exec bwrap "${args[@]}" /usr/bin/env -i HOME=/home/you USER=you LANG=C.UTF-8 LC_ALL=C.UTF-8 TMPDIR=/home/you/tmp \
  XDG_DATA_HOME=/home/you/.local/share XDG_CONFIG_HOME=/home/you/.config XDG_CACHE_HOME=/home/you/.cache \
  GIT_CONFIG_GLOBAL=/home/you/.gitconfig GIT_CONFIG_NOSYSTEM=1 PLAYWRIGHT_BROWSERS_PATH="$pw" "$@"
