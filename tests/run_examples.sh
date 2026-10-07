#!/usr/bin/env bash
# Build every example inside the builder image and check what comes out.
# Run from the repo root, inside the image:
#   docker run --rm -v "$PWD:/repo" -w /repo ghuser-builder:dev tests/run_examples.sh
# CI runs the same script against the freshly built image.
set -euo pipefail

ROOT="$(pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

build() {  # build <example> <expected .yak name> [extra ghuser-build args...]
  local ex="$1" yak="$2"; shift 2
  echo "== $ex"
  cp -r "$ROOT/examples/$ex" "$WORK/$ex"
  (cd "$WORK/$ex" && ghuser-build --version 1.2.3 --yak "${yak%%-1.2.3*}" "$@" components dist)
  [[ -f "$WORK/$ex/dist/$yak" ]] || fail "$ex: $yak was not written"
  unzip -p "$WORK/$ex/dist/$yak" manifest.yml > "$WORK/$ex/manifest.yml"
  grep -q '^version: 1.2.3$' "$WORK/$ex/manifest.yml" || fail "$ex: manifest version"
  grep -q '^authors:$' "$WORK/$ex/manifest.yml" || fail "$ex: manifest authors"
}

build 01-standalone rccn-spiral-1.2.3-rh8_0-any.yak
unzip -l "$WORK/01-standalone/dist/rccn-spiral-1.2.3-rh8_0-any.yak" | grep -q 'Spiral.ghuser' || fail "01: .ghuser missing from .yak"

build 02-with-core rccn-ringkit-1.2.3-rh8_0-any.yak
unzip -l "$WORK/02-with-core/dist/rccn-ringkit-1.2.3-rh8_0-any.yak" | grep -q ' icon.png' || fail "02: package icon missing"

build 03-vendored-core rccn-ringkit-vendored-1.2.3-rh8_0-any.yak --yak-include src/ringkit:lib/ringkit
unzip -l "$WORK/03-vendored-core/dist/rccn-ringkit-vendored-1.2.3-rh8_0-any.yak" | grep -q 'lib/ringkit/__init__.py' \
  || fail "03: vendored core missing from .yak"

# {{version}} really is substituted: the verifier compares against the substituted
# source, so check the opposite case fails -- a verifier that cannot fail checks nothing.
echo "== verifier rejects a wrong version"
if python3 /opt/ghuser-builder/tools/verify_ghuser.py --version 9.9.9 \
     "$WORK/02-with-core/components" "$WORK/02-with-core/dist/ghuser" >/dev/null; then
  fail "verifier accepted a .ghuser built for 1.2.3 as 9.9.9"
fi

echo "== name prefix is applied and verified"
(cd "$WORK/01-standalone" && ghuser-build --prefix "RCCN " --version 1.2.3 components dist-prefix)

echo "== untagged builds get a dev version that is valid semver and PEP 440"
(cd "$WORK/01-standalone" && env -u CI_COMMIT_TAG CI_PIPELINE_IID=42 ghuser-build --yak rccn-spiral components dist-dev)
[[ -f "$WORK/01-standalone/dist-dev/rccn-spiral-0.0.0-dev.42-rh8_0-any.yak" ]] || fail "dev version naming"

echo "== make_yak rejects bad input"
python3 /opt/ghuser-builder/tools/make_yak.py --name ok --version 1.2 "$WORK/01-standalone/dist/ghuser" "$WORK" 2>/dev/null \
  && fail "accepted non-semver version"
python3 /opt/ghuser-builder/tools/make_yak.py --name "bad name" --version 1.2.3 "$WORK/01-standalone/dist/ghuser" "$WORK" 2>/dev/null \
  && fail "accepted package name with a space"

echo "ALL EXAMPLES OK"
