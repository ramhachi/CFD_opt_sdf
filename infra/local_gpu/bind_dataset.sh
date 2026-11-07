#!/bin/sh
# Optional absolute input mapping. Ordinary harness v1.1 uses no dataset.
set -eu
[ "$#" -eq 3 ] || { echo 'usage: bind_dataset.sh mount|unmount DATASET SLUG' >&2; exit 2; }
action=$1
dataset=$2
slug=$3
case "$slug" in ''|*[!A-Za-z0-9_-]*) echo 'invalid dataset slug' >&2; exit 2;; esac
target=/kaggle/input/$slug
[ -d "$dataset" ] || { echo 'dataset directory missing' >&2; exit 2; }
[ ! -L "$target" ] || { echo 'refusing symlink mount target' >&2; exit 2; }
case "$action" in
  mount)
    if mountpoint -q "$target"; then echo 'refusing existing mount' >&2; exit 2; fi
    mkdir -p "$target"
    [ -z "$(ls -A "$target")" ] || { echo 'refusing nonempty input directory' >&2; exit 2; }
    mount --bind "$dataset" "$target"
    if ! mount -o remount,bind,ro "$target"; then umount "$target"; exit 1; fi
    ;;
  unmount)
    mountpoint -q "$target" || { echo 'expected bind mount missing' >&2; exit 2; }
    [ "$(stat -c '%d:%i' "$dataset")" = "$(stat -c '%d:%i' "$target")" ] || { echo 'mounted source differs' >&2; exit 2; }
    # The Python caller holds the exclusive namespace lease through this call.
    umount "$target"
    rmdir "$target"
    ;;
  *) echo 'unknown action' >&2; exit 2;;
esac
