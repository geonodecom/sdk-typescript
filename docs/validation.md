# Standalone preparation validation

Checked locally on 2026-10-21.

34 tests across 4 files passed; Biome lint, TypeScript typecheck and build passed; npm pack dry-run passed with 353 files; built ESM import smoke passed. npm audit reports zero advisories after updating development-only Vitest to ^4.1.11 (locked 4.1.12).

Generated SDK runtime files are unchanged from the subtree split. Package name and version remain unchanged. The complete original consumer README is retained byte-for-byte in `docs/guide.md`. Shell scripts pass `bash -n`; Python maintainer scripts parse; the included OpenAPI contract has no `/v1/internal/` paths.

A high-confidence pattern scan of all preserved-history blobs (200) and working source files found no private-key, GitHub-token, AWS-access-ID, npm-token, PyPI-token or Slack-token patterns. This is a bounded pattern scan, not a comprehensive secrets audit.

No live authenticated API requests, package publication, remote repository changes or trusted-publisher changes were performed. Full regeneration was not executed because the OpenAPI generator toolchain was not installed in this preparation environment. Before enabling releases, run generation in a disposable checkout, review the diff and complete the migration described in [source-provenance.md](source-provenance.md).
