#!/usr/bin/env bash
# Lay a restored-and-refreshed S3 mirror over the working tree.
#
# Why this exists: the Intraday refresh and the Deploy site build each pulled
# the same ~570-600 MB bounded set out of the artifacts bucket on every run
# (latest.json for every agency plus today's and yesterday's dated snapshots),
# about eight cycles a day. The mirror keeps that set in the Actions cache, so
# `aws s3 sync --exact-timestamps --delete` into the mirror transfers only the
# objects S3 changed since the mirror was saved. This script then does what the
# old direct sync did to the working tree, from local files.
#
# The mirror is only a cache of what the sync just made equal to S3, with one
# exception this script handles: a dated snapshot from an earlier day. The sync
# filters name today's and yesterday's dated files only, so when the day rolls
# over the previous mirror's older dated files match neither the include list
# nor `--delete` and would be carried into the tree. Prune them first.
#
# Usage: overlay-s3-mirror.sh MIRROR_DIR DEST_DIR TODAY YESTERDAY
#   TODAY and YESTERDAY are YYYY-MM-DD, the same two days the sync included.
#
# The copy overwrites, as the direct sync did: a fresh checkout's files are
# always newer than the objects they stand in for, and the default download
# rule transfers when the local copy is newer.

set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 MIRROR_DIR DEST_DIR TODAY YESTERDAY" >&2
  exit 2
fi

mirror="$1"
dest="$2"
today="$3"
yesterday="$4"

date_pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
for day in "$today" "$yesterday"; do
  if ! [[ "$day" =~ $date_pattern ]]; then
    echo "not a YYYY-MM-DD date: ${day}" >&2
    exit 2
  fi
done

if [ ! -d "$mirror" ]; then
  echo "mirror directory does not exist: ${mirror}" >&2
  exit 2
fi

# Only an agency's own dated snapshots (<id>/<date>.json) are pruned. The
# aggregate directories are synced whole and legitimately hold date-named files
# (changes/2026-10-20.json), so they are left alone.
find "$mirror" -mindepth 2 -maxdepth 2 -type f \
  -name '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json' \
  ! -path "${mirror}/changes/*" \
  ! -path "${mirror}/rollups/*" \
  ! -path "${mirror}/run/*" \
  ! -name "${today}.json" \
  ! -name "${yesterday}.json" \
  -delete

mkdir -p "$dest"
cp -a "${mirror}/." "${dest}/"
