# Source provenance and release migration

This repository preserves the history of `typescript-sdk/` from `geonodecom/scraper-api-sdks`.

- Original source commit: `b9ebe5d53bd1b74a9de3f17d33e62e4f9054eea0` (the source repository's `dev` branch at extraction).
- Subtree split commit: `86a9e8a57330a842a521ccb37c319305b5644360`.
- Extraction: independent clone, `git subtree split --prefix=typescript-sdk`, then a single-branch clone renamed to `main`.
- License: inherited MIT license, copyright 2026 Geonode Team.
- Package and import names, API behavior and package version are unchanged.
- Original consumer README is retained in [guide.md](guide.md).

The public OpenAPI contract, generator configuration, filtering helper and ignore rules were copied from that same source commit. Internal `/v1/internal/` paths are filtered out. Generator and postprocessing paths were adapted to this repository root. The original monorepo remains the release authority until migration is explicitly completed.

## Publishing is not migrated

Package publishing still runs from the original repository. No publishing workflow, registry release or trusted-publisher change was made here. Do not publish the existing version again. The new repository metadata describes this source location; it is not proof that a new package release has shipped.

Before releasing from this repository, maintainers must coordinate the source of truth, configure registry trusted publishing for this repository, migrate the release workflow and approval environments, run a validation-only release, then publish a new version after review. Review generated output against the API contract before accepting regeneration changes.

## Regeneration

`bash scripts/generate.sh` uses the included contract and the generator version recorded in `.openapi-generator/VERSION`. Install `uv` (recommended) or the matching `openapi-generator-cli` and Java runtime first. Python 3 is also required for filtering and postprocessing. Regeneration is a maintainer task; SDK consumers do not need these tools.

## Signup offer release check

The README uses the product-owner-approved launch copy, “Sign up to get 10,000 free credits” (21 October 2026). Before public release, verify that the live signup flow and account credit allocation match this offer. This copy update does not configure billing or issue credits.

## Cross-link deployment handoff

The README and package homepage link to the live [integrations hub](https://geonode.com/integrations). The intended detail destination is `https://geonode.com/integrations/typescript`; it is a deployment target, not a verified public page. After that detail page is deployed and checked, replace the hub fallback in README/package metadata with the detail URL and retain an API documentation link.

Source metadata targets `https://github.com/geonodecom/sdk-typescript`; the repository remains private until its separate release decision. These local metadata edits do not alter an existing PyPI/npm listing. Carry them into the authoritative publishing source at the coordinated next release, then verify the registry's rendered README, source/issue links and homepage. Keep existing package names, versions and import identifiers unchanged during preparation.
