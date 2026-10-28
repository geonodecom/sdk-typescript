# Changelog

All notable changes to the TypeScript SDK will be documented in this file.

The format is inspired by Keep a Changelog.

## [Unreleased]

- Removed the internal repository preparation notes and links to the old monorepo.

- Docs links point to the package's page at https://docs.geonode.com/docs/scraper-api/guides/sdks/typescript.

- Prepare standalone source repository with documentation and self-contained maintainer tooling. Package name and version are unchanged.
- Update development-only Vitest tooling and its lockfile; contributors need Node.js 20, 22 or 24+. SDK runtime requirements are unchanged.


- README rewritten so it can be published as the TypeScript SDK page on docs.geonode.com: setup, common tasks including background jobs and webhooks, request options, errors and a method reference. The examples no longer set a placeholder `basePath`, so they call the production API as written.

## [0.6.1] - 2026-10-21

- The package page links to geonode.com, the Scraper API docs and sign-up.
- README: a sign-up link near the top.

## [0.6.0] - 2026-10-19

- Requests from Node.js and other non-browser runtimes now send `User-Agent: geonode-ts-sdk/<version>`. A `User-Agent` set in `Configuration.headers` still wins. Browsers send their own, as before.
- `Configuration` without a `basePath` now points at the production API, `https://scraper.geonode.io`, instead of `http://localhost`.
- `package-lock.json` carried version 0.4.0; it now matches `package.json`.

## [0.5.0] - 2026-09-16

- `ExtractRequest`: added `timeout`, the per-request budget in milliseconds counted from receipt and including queue wait. Sync requests only.
- `SearchRequest` and `SearchResponse`: added `engine`, so a caller can choose the search engine and see which one answered.
- `ErrorResponse`: added `details` for additional error context.
- `ExtractionError`: added `correlationId` of the failed extraction.
- `JobCollectionResponse`: added `isCapped`.
- `ExtractionErrorCode`: added `CANCELLED`.
- Removed `SearchErrorResponse`, which the API no longer returns.

## [0.4.0] - 2026-07-15

- Added `SearchApi` with `searchV1SearchPost`, `listSearchJobsV1SearchJobsGet`, `getSearchJobV1SearchJobIdGet`, each with error handling.
- Added response models `SearchRequest`, `SearchResponse`, `SearchHitModel`, `SearchErrorResponse`, `SearchJobDetailResponse`, `SearchJobsResponse`, `SearchListItemResponse`.
- Added `UsageApi` with `getConcurrencyUsageV1UsageConcurrencyGet`, and the `ConcurrencyUsageResponse` model, with error handling.
- `MapRequest.includeSubdomains` now defaults to `false` (previously `true`); discovery is scoped to the exact seed host by default.
- `MapResponse` gained an optional `metadata` field (`MapMetadata`) with discovery duration and link-count diagnostics.
- The API-key security scheme was renamed `APIKeyHeader` → `ApiKeyAuth` (no consumer-facing changes — the generated client already targeted the `X-Api-Key` header directly).
- One more internal-only endpoint is intentionally excluded from the SDK.

## [0.3.0] - 2026-06-11

- Added job-listing methods: `BatchApi.listBatchJobsV1BatchJobsGet`, `CrawlApi.listCrawlJobsV1CrawlJobsGet`, `MapApi.listMapJobsV1MapJobsGet`, and `MapApi.getMapJobV1MapJobIdGet`, each with error handling.
- Added response models `BatchJobsResponse`, `BatchListItemResponse`, `CrawlJobsResponse`, `CrawlListItemResponse`, `MapJobsResponse`, `MapListItemResponse`, `MapJobDetailResponse`.
- `CrawlRequest`/`CrawlConfig`: `proxy` now references `ProxySettings` (the `CrawlProxySettings` model was removed).
- `ExtractRequest`: removed `extractLinks`. `ExtractionData`: removed `links`.
- Internal-only endpoints are intentionally excluded from the SDK.

## [0.2.0] - 2026-06-03

- Added `BatchApi`, `CrawlApi`, `MapApi`, `WebhooksApi` with full error handling.
- Added `WaitConfig`, `WaitUntil` models for browser wait policy control.
- `ExtractRequest`: added `extractLinks` and `waitConfig` fields.
- `ExtractionData`: added optional `links` field.
- `ExtractionMetadata`: removed `retryCount` and `engineUsed`; added `waitConfig`.
- `ExtractionErrorCode`: added `WORK_CONCURRENCY_LIMITED`, `WORK_CONCURRENCY_LEASE_EXPIRED`, `INVALID_WAIT_FOR_SELECTOR`, `WAIT_FOR_SELECTOR_TIMEOUT`.

## [0.1.0] - 2026-04-13

- Initial TypeScript SDK scaffolding, generation workflow, and npm publishing automation.
