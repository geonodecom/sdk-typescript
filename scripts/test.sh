#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sdk_dir="$(cd "$script_dir/.." && pwd)"

if ! command -v npm >/dev/null 2>&1; then
  printf 'Install Node.js and npm before running TypeScript SDK tests.\n' >&2
  exit 1
fi

cd "$sdk_dir"
npm exec -- vitest run "$@"
