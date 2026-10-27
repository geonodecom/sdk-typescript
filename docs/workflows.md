# TypeScript SDK: workflow recipes and output guide

[Repository overview](../README.md) · [Geonode documentation](https://www.npmjs.com/package/@geonode_scraper/scraper-sdk)

## Understand the extraction result

The TypeScript quick start requests Markdown and reads data.markdown from a completed extraction. Request HTML when you need data.html. Keep metadata.url alongside the content so later processing retains its source. tokens_charged reports the request's usage.

A background request returns a job ID and status instead of immediately returning finished content. Keep that ID, retrieve the job and inspect its terminal status before reading the result. A timeout after submission is not a reason to submit the same job again.

## Example: prepare website content for retrieval

1. Start with a small list of source URLs, or map a site and select the relevant pages.
2. Extract Markdown from one URL and inspect its content and source metadata before processing the list.
3. Use a batch for a known URL list, or a crawl with explicit depth and page limits when you need linked pages.
4. Pass completed content to your own chunking and embedding pipeline, then store the chunks with their source URLs and retrieval time.
5. Handle failed pages separately so partial results do not silently become a complete dataset.

**Expected result:** Page content and source metadata are ready for your application. Embeddings, vector storage, product-field parsing and change detection are separate steps you supply.

## Setup questions

Missing content? Confirm the requested format and whether the job has completed. Enable JavaScript rendering when the target depends on a browser, and inspect the returned status and error details.

Where does the API key belong? Keep it in your server environment and pass it through the SDK configuration. A browser application should call your own server instead of exposing the key.

Does installing the SDK run a scraper locally? It installs an API client. Extraction runs through the hosted Geonode service and uses your account's allowance.

Need MCP? Use the separate hosted MCP connection for a compatible assistant; this SDK does not start an MCP server.

Source-reviewed recipes; authenticated workflow execution has not been tested in this review.
