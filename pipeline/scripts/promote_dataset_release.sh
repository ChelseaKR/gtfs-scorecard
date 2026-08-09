#!/usr/bin/env bash
# Publish a staged dataset release from one successful, immutable workflow package.
set -euo pipefail

if [ "$#" -ne 2 ] || [[ ! "$1" =~ ^dataset-[0-9]{4}-[0-9]{2}$ ]] \
  || [[ ! "$2" =~ ^[1-9][0-9]*$ ]]; then
  echo "usage: $0 dataset-YYYY-MM WORKFLOW_RUN_ID" >&2
  exit 2
fi

tag=$1
workflow_run_id=$2
repository=ChelseaKR/gtfs-scorecard
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

for command in gh git jq uv; do
  command -v "$command" >/dev/null || {
    echo "error: required command is missing: $command" >&2
    exit 1
  }
done

cd "$repo_root"
if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  echo "error: promotion requires a clean checkout" >&2
  exit 1
fi
git fetch origin main
if [ "$(git branch --show-current)" != main ] \
  || [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "error: promotion requires current origin/main" >&2
  exit 1
fi

run_json=$(gh run view "$workflow_run_id" --repo "$repository" \
  --json attempt,conclusion,event,name)
workflow_run_attempt=$(jq -er '
  select(.name == "Dataset release" and .conclusion == "success"
    and (.event == "schedule" or .event == "workflow_dispatch"))
  | .attempt | select(type == "number" and . >= 1)
' <<<"$run_json")

promotion_tmp=$(mktemp -d)
cleanup() { rm -rf "$promotion_tmp"; }
trap cleanup EXIT
package="$promotion_tmp/package"
mkdir -p "$package"
artifact="dataset-release-promotion-${tag}-${workflow_run_id}-${workflow_run_attempt}"
gh run download "$workflow_run_id" --repo "$repository" \
  --name "$artifact" --dir "$package"

test -f "$package/promotion.json"
test -f "$package/notes.md"
test -d "$package/bundle"
if find "$package" -type l | grep -q .; then
  echo "error: promotion package contains a symbolic link" >&2
  exit 1
fi

target=$(jq -er --arg repository "$repository" --arg tag "$tag" \
  --argjson workflow_run_id "$workflow_run_id" \
  --argjson workflow_run_attempt "$workflow_run_attempt" '
  select(keys == ["repository", "schema_version", "source_mode",
    "source_run_attempt", "source_run_id", "tag", "target", "title",
    "workflow_run_attempt", "workflow_run_id"])
  | select(.schema_version == 1 and .repository == $repository and .tag == $tag
    and .workflow_run_id == $workflow_run_id
    and .workflow_run_attempt == $workflow_run_attempt
    and (.target | test("^[0-9a-f]{40}$"))
    and .title == ("Dataset " + ($tag | sub("^dataset-"; "")))
    and (.source_mode == "scheduled-daily" or .source_mode == "manual-latest")
    and (.source_run_id | type == "number")
    and (.source_run_attempt | type == "number"))
  | .target
' "$package/promotion.json")

git fetch origin "refs/tags/${tag}:refs/tags/${tag}"
test "$(git cat-file -t "refs/tags/${tag}")" = tag
test "$(git rev-parse "refs/tags/${tag}^{commit}")" = "$target"
git config --local gpg.format ssh
git config --local gpg.ssh.allowedSignersFile "$repo_root/.github/release-signers"
git verify-tag -- "$tag"

local_tag_object=$(git rev-parse "refs/tags/${tag}")
hosted_ref=$(gh api "repos/${repository}/git/ref/tags/${tag}")
jq -e --arg object "$local_tag_object" \
  '.object.type == "tag" and .object.sha == $object' <<<"$hosted_ref" >/dev/null
hosted_tag=$(gh api "repos/${repository}/git/tags/${local_tag_object}")
jq -e --arg target "$target" \
  '.object.type == "commit" and .object.sha == $target' <<<"$hosted_tag" >/dev/null

if [ -z "${GH_TOKEN:-}" ]; then
  GH_TOKEN=$(gh auth token)
  export GH_TOKEN
fi
source_mode=$(jq -r '.source_mode' "$package/promotion.json")
source_run_id=$(jq -r '.source_run_id' "$package/promotion.json")
source_run_attempt=$(jq -r '.source_run_attempt' "$package/promotion.json")
title=$(jq -r '.title' "$package/promotion.json")
uv run --project pipeline python -m scorecard_pipeline.dataset_release_promotion \
  --repository "$repository" \
  --tag "$tag" \
  --target "$target" \
  --title "$title" \
  --notes "$package/notes.md" \
  --bundle "$package/bundle" \
  --source-mode "$source_mode" \
  --source-run-id "$source_run_id" \
  --source-run-attempt "$source_run_attempt"
