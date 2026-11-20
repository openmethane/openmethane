#!/usr/bin/env bash
#
# Check that every binary in the image can find its shared libraries.
#
# Usage: check-binaries.sh [--command NAME]... FOLDER...
#
# Runs ldd on every ELF file under each FOLDER and fails, naming the file and
# library, if any library is "not found". Each --command NAME must also be on
# PATH, for programs that are run rather than linked, such as mpirun.
#
# The image copies the WRF and WPS binaries from another image, so their
# libraries are installed by name in the Dockerfile. This script is what keeps
# that list honest. When it reports a missing library, run
# `dpkg -S <library>` in the image the binary came from to find the package.
#
# ldd can't see libraries loaded at run time (dlopen), or data files. Running
# the programs for real is the only full check.

set -euo pipefail

commands=()
folders=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --command)
      commands+=("$2")
      shift 2
      ;;
    *)
      folders+=("$1")
      shift
      ;;
  esac
done

if [[ ${#folders[@]} -eq 0 ]]; then
  echo "usage: $0 [--command NAME]... FOLDER..." >&2
  exit 2
fi

failed=0

for command in "${commands[@]}"; do
  if ! command -v "$command" >/dev/null; then
    echo "MISSING COMMAND: $command is not on PATH" >&2
    failed=1
  fi
done

for folder in "${folders[@]}"; do
  if [[ ! -d "$folder" ]]; then
    echo "MISSING FOLDER: $folder" >&2
    failed=1
    continue
  fi

  checked=0
  while IFS= read -r -d '' file; do
    # Identify ELF files by their magic number, since `file` isn't installed.
    [[ "$(head -c 4 "$file" | tr -d '\0')" == $'\x7fELF' ]] || continue
    checked=$((checked + 1))

    # ldd exits non-zero for a static binary, which needs no libraries.
    # "lib.so => not found" is a missing library. "version `X' not found" is a
    # library too old for the binary, usually a different Debian release.
    while IFS= read -r line; do
      if [[ "$line" == *"=> not found"* ]]; then
        echo "MISSING LIBRARY: $file needs ${line%% =>*}" >&2
      else
        echo "WRONG LIBRARY VERSION: $file: $line" >&2
      fi
      failed=1
    done < <(ldd "$file" 2>&1 | grep "not found" | sed 's/^[[:space:]]*//' || true)
  done < <(find -L "$folder" -type f -print0)

  echo "checked $checked binaries under $folder"
  if [[ $checked -eq 0 ]]; then
    echo "NO BINARIES: $folder holds no ELF files, so the check proves nothing" >&2
    failed=1
  fi
done

if [[ $failed -ne 0 ]]; then
  echo "Binary check failed. Add the missing packages to the Dockerfile, or for a" >&2
  echo "wrong library version, check both images are on the same Debian release." >&2
  exit 1
fi
echo "All binaries found their libraries."
