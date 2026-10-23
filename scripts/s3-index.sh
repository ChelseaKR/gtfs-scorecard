#!/usr/bin/env bash
# Read and write the aggregate index (data/artifacts/index.json) in the
# artifacts bucket, whether it is stored as plain JSON or as gzip.
#
# Why this exists: index.json carries every agency's full history (151 MB on
# 2026-10-22) and every refresh, deploy, collect and report run read all of it
# from S3. The same bytes gzip to about 5 MB (31x). `aws s3 cp` and boto3 do not
# undo `Content-Encoding: gzip`, so the object cannot simply be re-uploaded
# compressed: every reader has to decode. This script is the one place the
# workflows do that, so a reader cannot be left behind.
#
# The key never changes, so there is still exactly one index object, the ETag
# guard in targeted-score.yml still means what it did, and no IAM policy needs
# a new key.
#
# Usage:
#   s3-index.sh get BUCKET DEST
#   s3-index.sh put BUCKET SRC [ETAG]
#
# get   downloads the object and writes DEST as plain JSON. A gzip body (the
#       two magic bytes 1f 8b) is decoded; anything else is taken as plain JSON,
#       so a reader works the same before and after the writers switch. DEST is
#       replaced only once the result is known to be a JSON object, never left
#       half written.
# put   uploads SRC. With INDEX_GZIP=1 it uploads gzip, labelled
#       Content-Encoding: gzip so a browser or `curl --compressed` still gets
#       JSON, after checking the compressed bytes decode back to SRC exactly.
#       Without it, it uploads SRC unchanged, which is what the workflows did
#       before this script. With ETAG, the write is conditional (If-Match) on
#       the exact object that was read.

set -euo pipefail

KEY="data/artifacts/index.json"
CACHE_CONTROL="max-age=300"

usage() {
  echo "usage: $0 get BUCKET DEST | put BUCKET SRC [ETAG]" >&2
  exit 2
}

[ "$#" -ge 3 ] || usage
action="$1"
bucket="$2"
path="$3"
[ -n "$bucket" ] || usage

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

case "$action" in
  get)
    [ "$#" -eq 3 ] || usage
    aws s3 cp "s3://${bucket}/${KEY}" "$scratch/stored" --only-show-errors
    magic="$(head -c 2 "$scratch/stored" | od -An -tx1 | tr -d ' \n')"
    if [ "$magic" = "1f8b" ]; then
      gzip -dc "$scratch/stored" > "$scratch/plain"
    else
      mv "$scratch/stored" "$scratch/plain"
    fi
    if [ "$(head -c 1 "$scratch/plain")" != "{" ]; then
      echo "s3://${bucket}/${KEY} is not a JSON object after decoding; DEST left untouched." >&2
      exit 1
    fi
    mkdir -p "$(dirname "$path")"
    mv "$scratch/plain" "$path.tmp.$$"
    mv "$path.tmp.$$" "$path"
    ;;
  put)
    [ "$#" -le 4 ] || usage
    etag="${4:-}"
    [ -s "$path" ] || { echo "no index to upload at ${path}" >&2; exit 1; }
    body="$path"
    encoding=()
    if [ "${INDEX_GZIP:-}" = "1" ]; then
      # -n: no name or timestamp in the header, so the same JSON is the same bytes.
      gzip -n -6 -c "$path" > "$scratch/body.gz"
      gzip -dc "$scratch/body.gz" | cmp -s - "$path" || {
        echo "compressed index does not decode back to ${path}; nothing uploaded." >&2
        exit 1
      }
      body="$scratch/body.gz"
      encoding=(--content-encoding gzip)
    fi
    if [ -n "$etag" ]; then
      aws s3api put-object \
        --bucket "$bucket" --key "$KEY" --body "$body" \
        --if-match "$etag" \
        --cache-control "$CACHE_CONTROL" \
        --content-type application/json \
        ${encoding[@]+"${encoding[@]}"} >/dev/null
    else
      aws s3 cp "$body" "s3://${bucket}/${KEY}" \
        --cache-control "$CACHE_CONTROL" \
        --content-type application/json \
        ${encoding[@]+"${encoding[@]}"} --only-show-errors
    fi
    ;;
  *)
    usage
    ;;
esac
