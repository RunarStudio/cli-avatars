#!/bin/bash
# netns.sh <home> <cmd…>: run cmd as you in a fresh network namespace (loopback only, no route out), clean env.
# Needs passwordless sudo for unshare; nothing in the recording can reach a network service.
home=$1; shift
exec sudo -n unshare -n -- /bin/sh -c '
  ip link set lo up || exit 1
  uid=$1 gid=$2 home=$3; shift 3
  exec setpriv --reuid="$uid" --regid="$gid" --init-groups -- /usr/bin/env -i HOME="$home" \
    PATH="$home/bin:/usr/local/bin:/usr/bin:/bin" LANG=C.UTF-8 LC_ALL=C.UTF-8 XDG_DATA_HOME="$home/.local/share" \
    XDG_CONFIG_HOME="$home/.config" XDG_CACHE_HOME="$home/.cache" TMPDIR="$home/tmp" "$@"' \
  sh "$(id -u)" "$(id -g)" "$home" "$@"
