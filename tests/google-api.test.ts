import { describe, expect, it } from "vitest";

import { BatchApi, Configuration, type ErrorResponse, GoogleApi } from "../src/index.js";
import { createJsonFetchMock, expectApiResponseError } from "./helpers.js";

function errorPayload(code: string, retryable = false) {
  return { code, message: `${code} message`, correlation_id: "corr-123", retryable };
}

function configuration(fetchApi: ReturnType<typeof createJsonFetchMock>["fetchApi"]) {
  return new Configuration({ basePath: "https://api.example.com", apiKey: "secret-key", fetchApi });
}

describe("error mapping of endpoints added by the API sync", () => {
  it.each([
    [402, "PAYMENT_REQUIRED"],
    [429, "RATE_LIMITED"],
    [503, "SERVICE_UNAVAILABLE"],
  ])("Google Search Light raises ApiResponseError for %i", async (status, code) => {
    const { fetchApi } = createJsonFetchMock(errorPayload(code), status);
    const api = new GoogleApi(configuration(fetchApi));

    const error = await expectApiResponseError<ErrorResponse>(
      api.googleSearchLightV1GoogleSearchLightPost({
        googleSearchLightRequest: { query: "geonode" },
      }),
      status,
    );

    expect(error.data?.code).toBe(code);
    expect(error.data?.correlationId).toBe("corr-123");
  });

  it("Google Shopping product raises ApiResponseError", async () => {
    const { fetchApi } = createJsonFetchMock(errorPayload("TIMEOUT", true), 408);
    const api = new GoogleApi(configuration(fetchApi));

    const error = await expectApiResponseError<ErrorResponse>(
      api.googleShoppingProductV1GoogleShoppingProductPost({
        googleShoppingProductRequest: { url: "https://www.google.com/shopping/product/1" },
      }),
      408,
    );

    expect(error.data?.retryable).toBe(true);
  });

  it("batch download raises ApiResponseError when the archive has expired", async () => {
    const { fetchApi } = createJsonFetchMock(errorPayload("GONE"), 410);
    const api = new BatchApi(configuration(fetchApi));

    const error = await expectApiResponseError<ErrorResponse>(
      api.downloadBatchResultsV1BatchJobIdDownloadGet({ jobId: "batch-123" }),
      410,
    );

    expect(error.data?.code).toBe("GONE");
  });
});
