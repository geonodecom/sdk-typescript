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

The runtime client is generated from `openapi.json`. Update the contract and generation/postprocessing scripts when changing generated behavior, and add a focused regression test. To regenerate, run `bash scripts/generate.sh`. It uses the included contract and the generator version recorded in `.openapi-generator/VERSION`. Install `uv` (recommended) or the matching `openapi-generator-cli` and a Java runtime first, plus Python 3 for filtering and postprocessing.

Every night the `Sync API spec` workflow compares `openapi.json` with production (`scripts/sync_openapi.py`, kept in step with the one in [geonodecom/sdk-python](https://github.com/geonodecom/sdk-python)), regenerates the client and keeps one pull request from the integrations bot up to date, on the `bot/openapi-sync` branch. It is labelled `breaking` or `additive` by oasdiff and adds a changelog entry under `[Unreleased]`. Review it like any other pull request; its "Needs attention" section lists what postprocessing could not do on its own, such as new methods missing from the error mappings. When a breaking change fails the tests, push the fixes to that branch: the workflow leaves a branch with commits from people alone until its pull request is merged or closed. Merging publishes nothing. To run the same comparison locally, use `python3 scripts/sync_openapi.py` and then `bash scripts/generate.sh`; `python3 -m pytest scripts/tests` tests the script.

## Reports and releases

For bugs, include the package version, runtime version, a minimal reproduction and expected behavior. Security reports belong in [SECURITY.md](SECURITY.md), not a public issue. Maintainers publish releases with the `Publish` workflow in GitHub Actions.
