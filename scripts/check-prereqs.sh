#!/usr/bin/env bash
set -euo pipefail

required_tools=(podman terraform sentinel curl openssl)

missing=0

for tool in "${required_tools[@]}"; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    printf 'missing required tool: %s\n' "${tool}" >&2
    missing=1
  fi
done

if ! podman compose version >/dev/null 2>&1; then
  printf 'missing podman compose support\n' >&2
  missing=1
fi

if [ "${missing}" -ne 0 ]; then
  exit 1
fi

printf 'all required demo tools are available\n'
