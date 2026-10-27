# Contributing to the Geonode TypeScript SDK

Open pull requests against `main`. Keep changes focused, describe the behavior and add an entry under `[Unreleased]` in `CHANGELOG.md`. Do not change package names or versions as part of routine fixes.

## Local checks

Use Node.js 20, 22 or 24+ for the current test tooling.

```sh
npm ci
npm run lint
npm test
npm run typecheck
npm run build
npm pack --dry-run
```

The tests use local fixtures and mocks; they do not require an API key. Never include credentials, customer data or account-specific output in a pull request.

## Generated code

The runtime client is generated from `openapi.json`. Update the contract and generation/postprocessing scripts when changing generated behavior, and add a focused regression test. See [source provenance](docs/source-provenance.md) for generator requirements and the release-migration boundary.

## Reports and releases

For bugs, include the package version, runtime version, a minimal reproduction and expected behavior. Security reports belong in [SECURITY.md](SECURITY.md), not a public issue. Publishing still runs from the original monorepo; these standalone repositories have no release workflow yet.
