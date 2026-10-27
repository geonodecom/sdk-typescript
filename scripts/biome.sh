#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sdk_dir="$(cd "$script_dir/.." && pwd)"
mode="${1:-check}"
shift || true

if ! command -v npm >/dev/null 2>&1; then
  printf 'Install Node.js and npm before running TypeScript SDK Biome checks.\n' >&2
  exit 1
fi

case "$mode" in
  check)
    cd "$sdk_dir" && npm exec -- biome check tests vitest.config.ts package.json biome.json "$@"
    ;;
  format)
    cd "$sdk_dir" && npm exec -- biome format --write tests vitest.config.ts package.json biome.json "$@"
    ;;
  *)
    printf 'Usage: %s [check|format] [additional-args...]\n' "$0" >&2
    exit 1
    ;;
esac
