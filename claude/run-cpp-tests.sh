#!/bin/bash
# Builds and runs the C++ test suites in build-tests/ (macOS/Homebrew), then points the generated
# config.h back at build/. CMake writes config.h (which records the build dir) into the source tree,
# so build/ and build-tests/ otherwise overwrite each other's copy: tests built against build/'s
# config.h fail their data-dir checks, and an app built against build-tests/'s cannot find its data.
#
# Usage: claude/run-cpp-tests.sh [test-binary ...]   (default: all four suites)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO}"
BREW_PREFIX="$(brew --prefix)"
export PKG_CONFIG_PATH="${BREW_PREFIX}/opt/icu4c/lib/pkgconfig:${BREW_PREFIX}/opt/curl/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
export LIBRARY_PATH="${BREW_PREFIX}/lib${LIBRARY_PATH:+:${LIBRARY_PATH}}"
SUITES=("$@")
[ ${#SUITES[@]} -gt 0 ] || SUITES=(run_tests_plusplus run_tests_no_x run_tests_with_x_1 run_tests_with_x_2)

restore_app_config() {
  [ -f build/CMakeCache.txt ] && cmake -S . -B build > /dev/null || true
}
trap restore_app_config EXIT

git submodule update --init tests/googletest > /dev/null
cmake -S . -B build-tests -GNinja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DINSTALL_GTEST='' > /dev/null
ninja -C build-tests "${SUITES[@]}"

status=0
for suite in "${SUITES[@]}"; do
  printf '%-22s ' "${suite}"
  if (cd build-tests && "./${suite}" > "${suite}.log" 2>&1); then
    grep -E '^\[  PASSED  \]' "build-tests/${suite}.log" || true
  else
    status=1
    grep -E '^\[  (PASSED|FAILED)  \]' "build-tests/${suite}.log" | tr '\n' ' '; echo
  fi
done
exit "${status}"
