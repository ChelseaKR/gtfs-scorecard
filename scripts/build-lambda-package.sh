#!/usr/bin/env bash
# Build the deployment package for one zip-packaged Lambda module under infra/.
#
# The runbooks used to say `pip install ../../pipeline -t build && cp *.py build/`.
# On a Mac that vendors macOS wheels, and the Lambda runtime is Linux: the
# package then holds .so files the runtime cannot load, and the handler dies on
# import with a ModuleNotFoundError naming the compiled submodule rather than
# the wheel (`No module named 'rpds.rpds'`, from jsonschema -> rpds-py). Nothing
# catches that before the first real request, because a zip that unpacks is
# still a zip that deploys.
#
# So: pull wheels for the runtime's platform explicitly, and refuse to hand back
# a package that holds a binary for any other one. The check is on the bytes, not
# on the wheel tag in the filename, so a mis-tagged wheel cannot pass it either.
#
# Usage (from the repository root):
#   scripts/build-lambda-package.sh infra/program-bundle
#   scripts/build-lambda-package.sh infra/submit
#
# Then `terraform -chdir=<module> apply` as the module's own runbook says. This
# script never touches Terraform, AWS, or the network beyond PyPI.

set -euo pipefail

# The Lambda runtime the modules declare (`runtime = "python3.12"`, and no
# `architectures`, which is x86_64). Change these together with main.tf.
PLATFORM="manylinux2014_x86_64"
PYTHON_VERSION="3.12"
ELF_MAGIC="7f454c46"

usage() {
  echo "usage: scripts/build-lambda-package.sh <module-dir>   e.g. infra/program-bundle" >&2
  exit 2
}

[ "$#" -eq 1 ] || usage
MODULE="${1%/}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODULE_DIR="$REPO_ROOT/$MODULE"

[ -d "$MODULE_DIR" ] || { echo "no such module directory: $MODULE_DIR" >&2; exit 2; }
[ -f "$MODULE_DIR/main.tf" ] || { echo "$MODULE is not a Terraform module (no main.tf)" >&2; exit 2; }

HANDLERS=("$MODULE_DIR"/*.py)
[ -e "${HANDLERS[0]}" ] || { echo "$MODULE has no handler .py files to package" >&2; exit 2; }

BUILD="$MODULE_DIR/build"
echo "== $MODULE: building $BUILD for $PLATFORM / CPython $PYTHON_VERSION"
rm -rf "$BUILD"

# --only-binary=:all: is what makes --platform meaningful: pip may not build a
# wheel from source here, because a source build would target this machine.
python3 -m pip install "$REPO_ROOT/pipeline" -t "$BUILD" \
  --platform "$PLATFORM" \
  --python-version "$PYTHON_VERSION" \
  --implementation cp \
  --only-binary=:all: \
  --quiet

cp "${HANDLERS[@]}" "$BUILD/"

# Every compiled extension in the package must be an ELF object, which is what
# the Linux runtime can load. A Mach-O (macOS) or PE (Windows) binary here is
# the bug this script exists to catch, and it is a hard failure: a package that
# is wrong in this way deploys cleanly and fails at the first import.
foreign=0
while IFS= read -r so; do
  magic="$(od -An -tx1 -N4 "$so" | tr -d ' \n')"
  if [ "$magic" != "$ELF_MAGIC" ]; then
    echo "not a Linux (ELF) binary: ${so#"$BUILD"/} (magic $magic)" >&2
    foreign=$((foreign + 1))
  fi
done < <(find "$BUILD" -name '*.so' -type f)

if [ "$foreign" -ne 0 ]; then
  echo "refusing this package: $foreign compiled file(s) are not Linux builds." >&2
  echo "Nothing was deployed. Re-run this script; do not fall back to a plain pip install." >&2
  exit 1
fi

total_so="$(find "$BUILD" -name '*.so' -type f | wc -l | tr -d ' ')"
echo "== $MODULE: ok — $total_so compiled file(s), all Linux/ELF; handlers: $(basename -a "${HANDLERS[@]}" | tr '\n' ' ')"
