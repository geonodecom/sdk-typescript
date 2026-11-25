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

Every night the `Sync API spec` workflow compares `openapi.json` with production (`scripts/sync_openapi.py`, kept in step with the one in [geonodecom/sdk-python](https://github.com/geonodecom/sdk-python)), regenerates the client and keeps one pull request from the integrations bot up to date, on the `bot/openapi-sync` branch. It is labelled `breaking` or `additive` by oasdiff and adds a changelog entry under `[Unreleased]`. Review it like any other pull request; its "Needs attention" section lists what postprocessing could not do on its own, such as new methods missing from the error mappings. When a breaking change fails the tests, push the fixes to that branch: the workflow leaves a branch with commits from people alone until its pull request is merged or closed. Merging publishes nothing. To run the same comparison locally, use `python3 scripts/sync_openapi.py` and then `bash scripts/generate.sh`; `python3 -m pytest scripts/tests` tests the scripts.

## Reports and releases

For bugs, include the package version, runtime version, a minimal reproduction and expected behavior. Security reports belong in [SECURITY.md](SECURITY.md), not a public issue.

To release, run the `Prepare release` workflow on `main` with `patch`, `minor`, `major` or an exact version. It runs `scripts/release.py` (kept in step with the one in [geonodecom/sdk-python](https://github.com/geonodecom/sdk-python)), which sets the version in every file that records it and moves the `[Unreleased]` notes under that version, and opens a `Release X.Y.Z` pull request from the integrations bot. Review the notes, merge it, then run the `Publish` workflow on `main` with `publish_target` set to `npm`. A release pull request and the nightly sync pull request conflict in `CHANGELOG.md`. If the sync one is merged first, close the release pull request, delete its branch and run `Prepare release` again. If the release is merged first, the next nightly run rebuilds the sync pull request on top of it; if people have pushed to that pull request, resolve the conflict by keeping its entry under `[Unreleased]`. Before 1.0, a release with a breaking change takes a new minor version. `python3 scripts/release.py minor` makes the same edits locally.
