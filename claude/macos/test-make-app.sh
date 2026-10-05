#!/bin/bash
# Checks that make-app.sh builds a valid CherryTree++.app that launches this checkout's build.
# Usage: claude/macos/test-make-app.sh   (needs build/cherrytree; run ./build.sh release notests)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "${HERE}/../.." && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "${OUT}"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

VERSION="$(head -1 "${REPO}/debian/changelog" | sed -E 's/.*\(([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"
"${HERE}/make-app.sh" "${OUT}" > /dev/null

APP="${OUT}/CherryTree++.app"
PLIST="${APP}/Contents/Info.plist"
plist() { /usr/libexec/PlistBuddy -c "Print :$1" "${PLIST}"; }

[ -d "${APP}" ] || fail "bundle not created"
plutil -lint "${PLIST}" > /dev/null || fail "Info.plist is invalid"
[ "$(plist CFBundleExecutable)" = "CherryTree++" ] || fail "wrong CFBundleExecutable"
[ "$(plist CFBundleIdentifier)" = "com.github.bigbadbuff.cherrytree-plusplus" ] || fail "wrong bundle id"
[ "$(plist CFBundleShortVersionString)" = "${VERSION}" ] || fail "version is not ${VERSION}"
[ -x "${APP}/Contents/MacOS/CherryTree++" ] || fail "launcher is not executable"
grep -qF "${REPO}/build/cherrytree" "${APP}/Contents/MacOS/CherryTree++" || fail "launcher does not run this checkout"
[ -s "${APP}/Contents/Resources/CherryTree++.icns" ] || fail "icon missing"
file "${APP}/Contents/Resources/CherryTree++.icns" | grep -q "Mac OS X icon" || fail "icon is not an icns file"

reported="$("${APP}/Contents/MacOS/CherryTree++" --version 2>&1 | tail -1)"
[ "${reported}" = "CherryTree ${VERSION}" ] || fail "launcher did not run the build (got: ${reported})"

echo "PASS: CherryTree++.app ${VERSION}"
