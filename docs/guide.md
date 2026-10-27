# Geonode Scraper SDK for TypeScript

[Integrations page](https://geonode.com/integrations) · [Geonode API docs](https://docs.geonode.com/docs/scraper-api) · [TypeScript SDK setup guide](https://docs.geonode.com/docs/scraper-api/guides/sdks/typescript) · [GitHub source](https://github.com/geonodecom/sdk-typescript) · [Published package](https://www.npmjs.com/package/@geonode_scraper/scraper-sdk) · [Repository overview](../README.md)

**[Try Geonode for free](https://app.geonode.com/sign-up)**

The TypeScript SDK for the [Geonode Scraper API](https://geonode.com/products/scraper-api). It turns any web page into clean Markdown or HTML, and also crawls sites, maps their URLs, runs web searches and reports your usage. Package: [`@geonode_scraper/scraper-sdk` on npm](https://www.npmjs.com/package/@geonode_scraper/scraper-sdk).

## Before you start

- Node.js 18 or newer. The SDK uses the built-in `fetch`.
- A Geonode API key. Sign in to the [Geonode dashboard](https://app.geonode.com/), open **API Keys**, and create a key or copy an existing one.
- Call the API from your server. The SDK also runs in a browser, but an API key in browser code is visible to anyone who opens the page.

## Install

```sh
npm install @geonode_scraper/scraper-sdk
```

The package is scoped: use the full name, `@geonode_scraper/scraper-sdk`, in `npm install` and in `import`. The examples below are ES modules with top-level `await`, so run them as `.mjs` or `.mts` files, or set `"type": "module"` in your `package.json`.

## Authenticate

Every request sends your key in the `X-Api-Key` header. Pass it once in `Configuration`. Keep the key out of your code, for example in an environment variable:

```ts
import { Configuration } from "@geonode_scraper/scraper-sdk"

const configuration = new Configuration({ apiKey: process.env.GEONODE_SCRAPER_API_KEY })
```

You don't need to set `basePath`: the client calls the production API, `https://scraper.geonode.io`. The examples below use this `configuration`.

## Your first request

Extract a page as Markdown. The call waits until the page is ready.

```ts
import { ExtractionApi, OutputFormat } from "@geonode_scraper/scraper-sdk"

const api = new ExtractionApi(configuration)
const response = await api.extractV1ExtractPost({
  extractRequest: { url: "https://example.com", formats: [OutputFormat.Markdown] }
})

if ("data" in response) {
  console.log(response.data.markdown)
  console.log(response.tokensCharged) // what this request cost
}
```

`extractV1ExtractPost` returns either the result or, in background mode, a job. The `"data" in response` check tells TypeScript which one you have.

## Common tasks

### Render JavaScript, pick a country, wait for an element

```ts
import { OutputFormat, ProxyType, WaitUntil, type ExtractRequest } from "@geonode_scraper/scraper-sdk"

const request: ExtractRequest = {
  url: "https://example.com/products",
  formats: [OutputFormat.Markdown],
  renderJs: true, // use a headless browser
  proxy: { country: "DE", type: ProxyType.Residential },
  waitConfig: { waitUntil: WaitUntil.Networkidle, waitFor: "#content", waitTimeout: 2000 },
  timeout: 60000 // give up after 60 s
}
```

All options are in [Request options](#request-options).

### Run an extraction in the background

Send the request with `ProcessingMode.Async` to get a job ID at once, then check the job until it finishes.

```ts
import { ExtractionApi, JobStatus, ProcessingMode } from "@geonode_scraper/scraper-sdk"

const api = new ExtractionApi(configuration)
const done: string[] = [JobStatus.Completed, JobStatus.Failed, JobStatus.Cancelled]

const accepted = await api.extractV1ExtractPost({
  extractRequest: { url: "https://example.com", processingMode: ProcessingMode.Async }
})
if ("jobId" in accepted) {
  let job = await api.getJobResultV1ExtractJobIdGet({ jobId: accepted.jobId })
  while (!done.includes(job.status)) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    job = await api.getJobResultV1ExtractJobIdGet({ jobId: accepted.jobId })
  }

  if (job.status === JobStatus.Completed) {
    console.log(job.data?.html)
  } else {
    console.log(job.status, job.error)
  }
}
```

To be notified instead of checking, use [webhooks](#get-notified-with-webhooks).

### Extract many URLs at once (batch)

```ts
import { BatchApi, OutputFormat } from "@geonode_scraper/scraper-sdk"

const api = new BatchApi(configuration)
const accepted = await api.createBatchV1BatchPost({
  batchRequest: { urls: ["https://example.com", "https://example.org"], formats: [OutputFormat.Markdown] }
})
const status = await api.getBatchStatusV1BatchJobIdGet({ jobId: accepted.jobId, page: 1, pageSize: 50 })
console.log(status.status, `${status.completedUrls}/${status.totalUrls}`)
for (const item of status.results ?? []) {
  console.log(item.url, item.status)
}
```

Check the status again until it is `JobStatus.Completed`, as in the background example above. `results` comes in pages: use `page` and `pageSize`.

### Crawl a site

Start from one URL and follow links up to a depth and a page limit.

```ts
import { CrawlApi, OutputFormat } from "@geonode_scraper/scraper-sdk"

const api = new CrawlApi(configuration)
const accepted = await api.createCrawlV1CrawlPost({
  crawlRequest: { url: "https://example.com", depth: 2, limit: 50, formats: [OutputFormat.Markdown] }
})
console.log(accepted.jobId, accepted.estimatedPages)
const status = await api.getCrawlStatusV1CrawlJobIdGet({ jobId: accepted.jobId, page: 1, pageSize: 50 })
console.log(status.status, `${status.completedPages}/${status.totalPages}`)
```

### List a site's URLs (map)

Find the URLs under a site from its sitemap and links. Returns at once.

```ts
import { MapApi } from "@geonode_scraper/scraper-sdk"

const result = await new MapApi(configuration).mapUrlsV1MapPost({ mapRequest: { url: "https://example.com" } })
for (const link of result.links ?? []) {
  console.log(link.url, link.source)
}
```

Add `search: "pricing"` to keep only matching URLs.

### Search the web

```ts
import { SearchApi } from "@geonode_scraper/scraper-sdk"

const result = await new SearchApi(configuration).searchV1SearchPost({ searchRequest: { query: "geonode scraper api" } })
for (const hit of result.results) {
  console.log(hit.position, hit.title, hit.url)
}
```

### Get notified with webhooks

Subscribe a URL to an event. Every finished extraction then sends a POST to that URL.

```ts
import { WebhookEventType, WebhooksApi } from "@geonode_scraper/scraper-sdk"

const webhook = await new WebhooksApi(configuration).createWebhookV1WebhooksPost({
  webhookCreate: { url: "https://your-app.example/hooks/geonode", eventType: WebhookEventType.ExtractCompleted }
})
console.log(webhook.id, webhook.secret) // store the secret: it signs every delivery
```

Events: `ExtractCompleted`, `BatchCompleted`, `CrawlCompleted`. Each delivery is JSON with `event`, `webhook_id`, `delivery_id`, `timestamp` and `data`. Check that a delivery comes from Geonode by comparing its `X-Webhook-Signature` header with an HMAC-SHA256 of the raw body:

```ts
import { createHmac, timingSafeEqual } from "node:crypto"

export function isFromGeonode(rawBody: Buffer | string, signatureHeader: string, secret: string): boolean {
  const expected = Buffer.from(`sha256=${createHmac("sha256", secret).update(rawBody).digest("hex")}`)
  const received = Buffer.from(signatureHeader)
  return expected.length === received.length && timingSafeEqual(expected, received)
}
```

Use the body exactly as it arrived, before any JSON parsing. Answer with any 2xx status. A 429 or 5xx answer makes Geonode retry the delivery. `rotateSecretV1WebhooksWebhookIdRotateSecretPost` issues a new secret and invalidates the old one.

### Check usage

```ts
import { StatisticsApi, UsageApi } from "@geonode_scraper/scraper-sdk"

const usage = await new UsageApi(configuration).getConcurrencyUsageV1UsageConcurrencyGet()
console.log(`${usage.workConcurrencyInUse} of ${usage.workConcurrencyLimit} concurrent requests in use`)

const weekAgo = new Date(Date.now() - 7 * 24 * 3600 * 1000)
const stats = await new StatisticsApi(configuration).getStatisticsV1StatisticsGet({ startDate: weekAgo })
console.log(stats.extractionCount, stats.successRate, stats.periodTokensUsed)
```

## Request options

`ExtractRequest` fields. Batch and crawl take the same `formats`, `renderJs`, `proxy` and `waitConfig`.

| Field | Default | What it does |
|---|---|---|
| `url` | required | The page to extract. |
| `formats` | `[OutputFormat.Html]` | `Markdown`, `Html` or both. |
| `renderJs` | `false` | Load the page in a headless browser. Slower and costs more; use it when the content needs JavaScript. |
| `processingMode` | `Sync` | `Sync` waits for the result; `Async` returns a job ID at once. |
| `proxy` | residential, country from the URL | `type`: `Residential`, `Datacenter` or `Mix`. `country`: a two-letter code such as `"US"`. Without a country, the API picks one from the URL. |
| `headers` | none | Extra HTTP headers for the target. `Host` is ignored. On browser requests `Accept-Language` sets the browser's language. |
| `timeout` | the API's ceiling | Milliseconds the request may take, including any wait in the queue. Sync requests only; at least 1000. |
| `waitConfig` | adaptive | Browser waits, in this order: `waitUntil` (`Commit`, `Domcontentloaded`, `Load`, `Networkidle`), `waitFor` (a CSS selector, or an XPath starting with `//` or `xpath=`), `waitTimeout` (0 to 30000 ms). Setting it turns on `renderJs`. |

## Errors and limits

A failed request throws `ApiResponseError` with `status`, `body` (the parsed JSON), `data` (the typed error model, when the SDK recognises it) and `response` (the original `Response`, with its headers). A network failure with no response throws `FetchError`.

```ts
import { ApiResponseError, ExtractionApi } from "@geonode_scraper/scraper-sdk"

try {
  await new ExtractionApi(configuration).extractV1ExtractPost({ extractRequest: { url: "https://example.com" } })
} catch (error) {
  if (error instanceof ApiResponseError) {
    console.log(error.status, error.body)
    if (error.status === 429) {
      console.log("retry after", error.response.headers.get("Retry-After"), "seconds")
    }
  } else {
    throw error
  }
}
```

| Status | Meaning | Retry? |
|---|---|---|
| 401 | The API key is missing or wrong. | No |
| 402 | No active plan, or not enough balance. | After topping up |
| 403 | The target is blocked by Geonode's compliance list (`TARGET_BLOCKED`). Not charged. | No |
| 422 | Either the request is invalid (the body's `detail` names the bad fields), or the page could not be extracted. In the second case `error.code` says why, for example `PERMANENT_BLOCK` or `CAPTCHA_CHALLENGE`, and `error.retryable` says whether trying again can help. | Fix the request; retry only if `retryable` is true |
| 429 | Too many requests, or all your concurrent requests are in use. | Yes, after `Retry-After` |
| 503 | Temporarily unavailable. For browser pages, `Async` mode may still work. | Yes, with a delay |
| 504 | The request did not finish within its `timeout`. | Yes, or raise `timeout` |
| 500 | An error on our side. | Yes, with a delay |

More in [error handling](https://docs.geonode.com/docs/scraper-api/troubleshooting/error-handling). Prices per request type are on the [pricing page](https://docs.geonode.com/docs/scraper-api/additional-resources/pricing).

## Reference

| Class | Method | Endpoint |
|---|---|---|
| `ExtractionApi` | `extractV1ExtractPost` | `POST /v1/extract` |
| | `getJobResultV1ExtractJobIdGet` | `GET /v1/extract/{job_id}` |
| | `listJobsV1ExtractJobsGet` | `GET /v1/extract/jobs` |
| `BatchApi` | `createBatchV1BatchPost` | `POST /v1/batch` |
| | `getBatchStatusV1BatchJobIdGet` | `GET /v1/batch/{job_id}` |
| | `cancelBatchV1BatchJobIdDelete` | `DELETE /v1/batch/{job_id}` |
| | `listBatchJobsV1BatchJobsGet` | `GET /v1/batch/jobs` |
| `CrawlApi` | `createCrawlV1CrawlPost` | `POST /v1/crawl` |
| | `getCrawlStatusV1CrawlJobIdGet` | `GET /v1/crawl/{job_id}` |
| | `cancelCrawlV1CrawlJobIdDelete` | `DELETE /v1/crawl/{job_id}` |
| | `listCrawlJobsV1CrawlJobsGet` | `GET /v1/crawl/jobs` |
| `MapApi` | `mapUrlsV1MapPost` | `POST /v1/map` |
| | `listMapJobsV1MapJobsGet`, `getMapJobV1MapJobIdGet` | `GET /v1/map/jobs`, `GET /v1/map/{job_id}` |
| `SearchApi` | `searchV1SearchPost` | `POST /v1/search` |
| | `listSearchJobsV1SearchJobsGet`, `getSearchJobV1SearchJobIdGet` | `GET /v1/search/jobs`, `GET /v1/search/{job_id}` |
| `WebhooksApi` | `createWebhookV1WebhooksPost`, `listWebhooksV1WebhooksGet`, `getWebhookV1WebhooksWebhookIdGet`, `updateWebhookV1WebhooksWebhookIdPatch`, `deleteWebhookV1WebhooksWebhookIdDelete` | `/v1/webhooks` |
| | `listDeliveriesV1WebhooksWebhookIdDeliveriesGet`, `rotateSecretV1WebhooksWebhookIdRotateSecretPost` | `/v1/webhooks/{webhook_id}/…` |
| `UsageApi` | `getConcurrencyUsageV1UsageConcurrencyGet` | `GET /v1/usage/concurrency` |
| `StatisticsApi` | `getStatisticsV1StatisticsGet` | `GET /v1/statistics` |
| `SystemApi` | `healthCheckHealthGet` | `GET /health` |

Every method also has a `*Raw` variant that returns the response together with the parsed value. `Configuration` also takes `middleware`, `fetchApi` and `headers` if you need to change how requests are sent. Full request and response schemas are in the [API reference](https://docs.geonode.com/docs/scraper-api/v1/reference).

## Versions and support

- The latest version is on [npm](https://www.npmjs.com/package/@geonode_scraper/scraper-sdk). The API stays backward compatible, so code written for an older version keeps working; new API features arrive in a new SDK release.
- Outside the browser, requests send `User-Agent: geonode-ts-sdk/<version>`, which helps support see which version you use. Set your own `User-Agent` in `headers` to change it. Browsers don't let a page set this header, so the SDK leaves it out there.
- Questions or problems: [contact Geonode](https://geonode.com/contact).
