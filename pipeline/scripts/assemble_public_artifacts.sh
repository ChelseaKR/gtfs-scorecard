#!/usr/bin/env bash
# Assemble the public artifact tree from the mixed pipeline store.
#
# The source also contains private pipeline inputs (validator caches, export
# fingerprints, raw clearance candidates, run state, and corrected feed zips).
# Copying an agency directory wholesale makes every future internal filename
# public by default. This script does the opposite: only the documented public
# filenames cross the deployment boundary.

set -euo pipefail

source_root="${1:-data/artifacts}"
dest_root="${2:-_site/data/artifacts}"
index_path="${3:-${source_root}/index.json}"

if [ ! -f "$index_path" ]; then
  echo "Public artifact assembly needs an index: $index_path" >&2
  exit 1
fi

rm -rf "$dest_root"
mkdir -p "$dest_root"

copy_if_present() {
  local source="$1"
  local destination="$2"
  if [ -f "$source" ]; then
    mkdir -p "$(dirname "$destination")"
    cp "$source" "$destination"
  fi
}

# Root documents consumed by the site or documented public API.
for name in directory.json index.json scoring.json sensitivity.json canada-equity.json; do
  copy_if_present "$source_root/$name" "$dest_root/$name"
done

# Named change history: one current pointer plus dated public records.
if [ -d "$source_root/changes" ]; then
  for source in "$source_root/changes"/*.json; do
    [ -e "$source" ] || continue
    name="$(basename "$source")"
    if [ "$name" = "latest.json" ] || [[ "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$ ]]; then
      copy_if_present "$source" "$dest_root/changes/$name"
    fi
  done
fi

# Public program exports. Internal *.state.json and digest.md files are not
# part of the public contract and deliberately fail closed here.
if [ -d "$source_root/rollups" ]; then
  for source in "$source_root/rollups"/*; do
    [ -f "$source" ] || continue
    name="$(basename "$source")"
    if [ "$name" = "index.json" ] || [[ "$name" =~ ^[a-z0-9-]+\.(json|csv)$ ]]; then
      copy_if_present "$source" "$dest_root/rollups/$name"
    fi
  done
fi

# Registry-bounded agency outputs. A date-shaped JSON file is a score snapshot;
# every other allowed filename is named explicitly.
jq -r '.agencies | keys[]' "$index_path" | while IFS= read -r agency_id; do
  if [[ ! "$agency_id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || \
     [[ "$agency_id" =~ ^(changes|rollups|run)$ ]]; then
    echo "Unsafe agency id in artifact index: $agency_id" >&2
    exit 1
  fi
  agency_source="$source_root/$agency_id"
  [ -d "$agency_source" ] || continue
  for source in "$agency_source"/*; do
    [ -f "$source" ] || continue
    name="$(basename "$source")"
    case "$name" in
      latest.json|badge.json|badge.svg|conformance.json|mark.svg|geometry.geojson)
        copy_if_present "$source" "$dest_root/$agency_id/$name"
        ;;
      *)
        if [[ "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\.json$ ]]; then
          copy_if_present "$source" "$dest_root/$agency_id/$name"
        fi
        ;;
    esac
  done
done
