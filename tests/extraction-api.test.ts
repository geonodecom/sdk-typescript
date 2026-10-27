import { describe, expect, it } from "vitest";

import {
  Configuration,
  type ErrorResponse,
  ExtractionApi,
  ExtractionErrorCode,
  type ExtractionErrorResponse,
  type HTTPValidationError,
  JobStatus,
  OutputFormat,
  ProcessingMode,
} from "../src/index.js";
import { createJsonFetchMock, expectApiResponseError, getHeader } from "./helpers.js";

const syncResponsePayload = {
  data: { html: "<html><body>Example</body></html>", markdown: "# Example" },
  metadata: {
    url: "https://example.com",
    render_js: true,
    formats: ["markdown"],
    processing_mode: "sync",
  },
  tokens_charged: 7,
};

const asyncResponsePayload = {
  job_id: "job-123",
  status: "queued",
  status_url: "https://api.example.com/v1/extract/job-123",
  estimated_tokens: 12,
};

const jobStatusPayload = {
  job_id: "job-123",
  status: "completed",
  created_at: "2026-01-01T00:00:00.000Z",
  completed_at: "2026-01-01T00:00:05.000Z",
  data: { html: "<html />" },
  metadata: {
    url: "https://example.com",
    render_js: false,
    formats: ["html"],
    processing_mode: "sync",
  },
  tokens_charged: 10,
};

const jobCollectionPayload = {
  jobs: [
    {
      job_id: "job-123",
      status: "completed",
      url: "https://example.com",
      created_at: "2026-01-01T00:00:00.000Z",
    },
  ],
  page: 1,
  page_size: 100,
  page_count: 1,
};

const extractionValidationErrorPayload = {
  error: {
    code: "TIMEOUT",
    message: "Timed out while extracting",
    retryable: true,
    details: { stage: "render" },
  },
  tokens_charged: 7,
};

const pathValidationErrorPayload = {
  detail: [
    {
      loc: ["path", "job_id"],
      msg: "Input should be a valid UUID",
      type: "uuid_parsing",
    },
  ],
};

const queryValidationErrorPayload = {
  detail: [
    {
      loc: ["query", "page"],
      msg: "Input should be greater than or equal to 1",
      type: "greater_than_equal",
    },
  ],
};

function createErrorResponse(code: string, retryable: boolean) {
  return {
    code,
    message: `${code} message`,
    correlation_id: "corr-123",
    retryable,
  };
}

describe("ExtractionApi", () => {
  it("serializes a sync extract request and authenticates with X-Api-Key", async () => {
    const { calls, fetchApi } = createJsonFetchMock(syncResponsePayload);

    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const response = await api.extractV1ExtractPost({
      extractRequest: {
        url: "https://example.com",
        formats: [OutputFormat.Markdown],
        renderJs: true,
        processingMode: ProcessingMode.Sync,
        headers: { "User-Agent": "ts-sdk-test" },
      },
    });

    expect(calls).toHaveLength(1);
    expect(calls[0].input).toBe("https://api.example.com/v1/extract");
    expect(getHeader(calls[0].init, "X-Api-Key")).toBe("secret-key");
    expect(getHeader(calls[0].init, "Content-Type")).toBe("application/json");

    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      url: "https://example.com",
      formats: ["markdown"],
      render_js: true,
      processing_mode: "sync",
      headers: { "User-Agent": "ts-sdk-test" },
    });

    expect("data" in response).toBe(true);
    if ("data" in response) {
      expect(response.data.markdown).toBe("# Example");
      expect(response.tokensCharged).toBe(7);
    }
  });

  it("returns async job payloads for 202 extract responses", async () => {
    const { fetchApi } = createJsonFetchMock(asyncResponsePayload, 202);

    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const response = await api.extractV1ExtractPost({
      extractRequest: {
        url: "https://example.com",
        processingMode: ProcessingMode.Async,
      },
    });

    expect("jobId" in response).toBe(true);
    if ("jobId" in response) {
      expect(response.jobId).toBe("job-123");
      expect(response.statusUrl).toBe("https://api.example.com/v1/extract/job-123");
    }
  });

  it.each([
    [400, "BAD_REQUEST", false],
    [401, "UNAUTHORIZED", false],
    [402, "PAYMENT_REQUIRED", false],
    [429, "RATE_LIMITED", true],
    [500, "INTERNAL_ERROR", true],
    [503, "SERVICE_UNAVAILABLE", true],
  ])("deserializes extract error payloads for status %i", async (status, code, retryable) => {
    const payload = createErrorResponse(code, retryable);
    const { fetchApi } = createJsonFetchMock(payload, status);

    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<ErrorResponse | ExtractionErrorResponse>(
      api.extractV1ExtractPost({
        extractRequest: { url: "https://example.com" },
      }),
      status,
    );

    expect(error.data).toMatchObject({
      code,
      message: `${code} message`,
      correlationId: "corr-123",
      retryable,
    });
    expect(error.body).toEqual(payload);
  });

  it("deserializes 422 extraction error responses", async () => {
    const { fetchApi } = createJsonFetchMock(extractionValidationErrorPayload, 422);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<ExtractionErrorResponse>(
      api.extractV1ExtractPost({
        extractRequest: { url: "https://example.com" },
      }),
      422,
    );

    expect(error.data?.error.code).toBe(ExtractionErrorCode.Timeout);
    expect(error.data?.error.retryable).toBe(true);
    expect(error.data?.tokensCharged).toBe(7);
    expect(error.body).toEqual(extractionValidationErrorPayload);
  });

  it("deserializes job status responses", async () => {
    const { fetchApi } = createJsonFetchMock(jobStatusPayload);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const response = await api.getJobResultV1ExtractJobIdGet({ jobId: "job-123" });

    expect(response.jobId).toBe("job-123");
    expect(response.status).toBe(JobStatus.Completed);
    expect(response.completedAt).toBeInstanceOf(Date);
    expect(response.tokensCharged).toBe(10);
  });

  it.each([
    [401, "UNAUTHORIZED", false],
    [404, "NOT_FOUND", false],
  ])("deserializes get-job error payloads for status %i", async (status, code, retryable) => {
    const payload = createErrorResponse(code, retryable);
    const { fetchApi } = createJsonFetchMock(payload, status);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<ErrorResponse | HTTPValidationError>(
      api.getJobResultV1ExtractJobIdGet({ jobId: "job-123" }),
      status,
    );

    expect(error.data).toMatchObject({
      code,
      message: `${code} message`,
      correlationId: "corr-123",
      retryable,
    });
    expect(error.body).toEqual(payload);
  });

  it("deserializes get-job validation errors", async () => {
    const { fetchApi } = createJsonFetchMock(pathValidationErrorPayload, 422);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<HTTPValidationError>(
      api.getJobResultV1ExtractJobIdGet({ jobId: "bad-job-id" }),
      422,
    );

    expect(error.data?.detail?.[0]?.loc).toEqual(["path", "job_id"]);
    expect(error.data?.detail?.[0]?.msg).toBe("Input should be a valid UUID");
  });

  it("deserializes job collection responses", async () => {
    const { fetchApi } = createJsonFetchMock(jobCollectionPayload);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const response = await api.listJobsV1ExtractJobsGet();

    expect(response.jobs).toHaveLength(1);
    expect(response.jobs[0].jobId).toBe("job-123");
    expect(response.page).toBe(1);
    expect(response.pageCount).toBe(1);
  });

  it.each([
    [{ jobId: "job-123" }, { job_id: "job-123" }],
    [{ url: "https://example.com/path?q=1" }, { url: "https://example.com/path?q=1" }],
    [{ status: JobStatus.Completed }, { status: JobStatus.Completed }],
    [{ output: OutputFormat.Html }, { output: OutputFormat.Html }],
    [
      { startDate: new Date("2026-01-01T00:00:00.000Z") },
      { start_date: "2026-01-01T00:00:00.000Z" },
    ],
    [{ endDate: new Date("2026-01-07T23:59:59.000Z") }, { end_date: "2026-01-07T23:59:59.000Z" }],
    [
      { page: 2, pageSize: 10 },
      { page: "2", page_size: "10" },
    ],
  ])("serializes list-jobs filters %j", async (requestParameters, expectedQuery) => {
    const { calls, fetchApi } = createJsonFetchMock(jobCollectionPayload);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    await api.listJobsV1ExtractJobsGet(requestParameters);

    const url = new URL(calls[0].input);
    for (const [key, value] of Object.entries(expectedQuery)) {
      expect(url.searchParams.get(key)).toBe(value);
    }
    expect(getHeader(calls[0].init, "X-Api-Key")).toBe("secret-key");
  });

  it("serializes all list-jobs filters together", async () => {
    const { calls, fetchApi } = createJsonFetchMock(jobCollectionPayload);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    await api.listJobsV1ExtractJobsGet({
      jobId: "job-123",
      url: "https://example.com/path?q=1",
      status: JobStatus.Completed,
      output: OutputFormat.Markdown,
      startDate: new Date("2026-01-01T00:00:00.000Z"),
      endDate: new Date("2026-01-07T23:59:59.000Z"),
      page: 2,
      pageSize: 10,
    });

    const url = new URL(calls[0].input);
    expect(Object.fromEntries(url.searchParams.entries())).toEqual({
      job_id: "job-123",
      url: "https://example.com/path?q=1",
      status: JobStatus.Completed,
      output: OutputFormat.Markdown,
      start_date: "2026-01-01T00:00:00.000Z",
      end_date: "2026-01-07T23:59:59.000Z",
      page: "2",
      page_size: "10",
    });
  });

  it.each([
    [401, "UNAUTHORIZED", false],
    [404, "NOT_FOUND", false],
  ])("deserializes list-jobs error payloads for status %i", async (status, code, retryable) => {
    const payload = createErrorResponse(code, retryable);
    const { fetchApi } = createJsonFetchMock(payload, status);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<ErrorResponse | HTTPValidationError>(
      api.listJobsV1ExtractJobsGet({ jobId: "job-123" }),
      status,
    );

    expect(error.data).toMatchObject({
      code,
      message: `${code} message`,
      correlationId: "corr-123",
      retryable,
    });
    expect(error.body).toEqual(payload);
  });

  it("deserializes list-jobs validation errors", async () => {
    const { fetchApi } = createJsonFetchMock(queryValidationErrorPayload, 422);
    const api = new ExtractionApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<HTTPValidationError>(
      api.listJobsV1ExtractJobsGet({ page: 1 }),
      422,
    );

    expect(error.data?.detail?.[0]?.loc).toEqual(["query", "page"]);
    expect(error.data?.detail?.[0]?.msg).toBe("Input should be greater than or equal to 1");
  });
});
