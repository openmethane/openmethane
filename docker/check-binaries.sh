#!/usr/bin/env bash
#
# Check that every binary in the image can find its shared libraries.
#
# Usage: check-binaries.sh [--command NAME]... [--package NAME]... [FOLDER]...
#
# Runs ldd on every ELF file under each FOLDER, and in each installed Debian
# package NAME (the files listed by `dpkg -L`), and fails, naming the file and
# library, if any library is "not found". Each --command NAME must also be on
# PATH, for programs that are run rather than linked, such as mpirun.
#
# The model packages declare their own libraries in Depends, so this checks
# that apt resolved them all. The WRF and WPS binaries are copied from another
# image, so their libraries are installed by name in the Dockerfile, and this
# script is what keeps that list honest. When it reports a missing library for
# a folder, run `dpkg -S <library>` in the image the binary came from to find
# the package.
#
# ldd can't see libraries loaded at run time (dlopen), or data files. Running
# the programs for real is the only full check.

set -euo pipefail

commands=()
packages=()
folders=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --command)
      commands+=("$2")
      shift 2
      ;;
    --package)
      packages+=("$2")
      shift 2
      ;;
    *)
      folders+=("$1")
      shift
      ;;
  esac
done

if [[ ${#folders[@]} -eq 0 && ${#packages[@]} -eq 0 ]]; then
  echo "usage: $0 [--command NAME]... [--package NAME]... [FOLDER]..." >&2
  exit 2
fi

failed=0

for command in "${commands[@]}"; do
  if ! command -v "$command" >/dev/null; then
    echo "MISSING COMMAND: $command is not on PATH" >&2
    failed=1
  fi
done

# check_files LABEL: checks the ELF files whose paths arrive on stdin, NUL
# separated. Sets failed=1 on a problem.
check_files() {
  local label="$1" file line checked=0
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
  done

  echo "checked $checked binaries in $label"
  if [[ $checked -eq 0 ]]; then
    echo "NO BINARIES: $label holds no ELF files, so the check proves nothing" >&2
    failed=1
  fi
}

for folder in "${folders[@]}"; do
  if [[ ! -d "$folder" ]]; then
    echo "MISSING FOLDER: $folder" >&2
    failed=1
    continue
  fi
  check_files "$folder" < <(find -L "$folder" -type f -print0)
done

for package in "${packages[@]}"; do
  if ! dpkg -s "$package" >/dev/null 2>&1; then
    echo "MISSING PACKAGE: $package is not installed" >&2
    failed=1
    continue
  fi
  # dpkg -L also lists folders, which -f excludes
  check_files "package $package" < <(
    dpkg -L "$package" | while IFS= read -r path; do
      [[ -f "$path" ]] && printf '%s\0' "$path"
    done
  )
done

if [[ $failed -ne 0 ]]; then
  echo "Binary check failed. Add the missing packages to the Dockerfile, or for a" >&2
  echo "wrong library version, check the models and the image are on the same" >&2
  echo "Debian release." >&2
  exit 1
fi
echo "All binaries found their libraries."
