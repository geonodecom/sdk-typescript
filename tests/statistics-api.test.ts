import { describe, expect, it } from "vitest";

import {
  Configuration,
  type ErrorResponse,
  type HTTPValidationError,
  StatisticsApi,
} from "../src/index.js";
import { createJsonFetchMock, expectApiResponseError, getHeader } from "./helpers.js";

const statisticsPayload = {
  extraction_count: 42,
  previous_period_extraction_count: 30,
  success_rate: 0.95,
  average_extraction_duration: 812,
  period_tokens_used: 1234,
};

const statisticsValidationErrorPayload = {
  detail: [
    {
      loc: ["query", "start_date"],
      msg: "Input should be before end_date",
      type: "value_error",
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

describe("StatisticsApi", () => {
  it("serializes date filters and authenticates with X-Api-Key", async () => {
    const { calls, fetchApi } = createJsonFetchMock(statisticsPayload);

    const startDate = new Date("2026-04-13T10:00:00.000Z");
    const endDate = new Date("2026-04-13T11:00:00.000Z");

    const api = new StatisticsApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const response = await api.getStatisticsV1StatisticsGet({ startDate, endDate });

    expect(calls).toHaveLength(1);
    const url = new URL(calls[0].input);
    expect(url.pathname).toBe("/v1/statistics");
    expect(url.searchParams.get("start_date")).toBe(startDate.toISOString());
    expect(url.searchParams.get("end_date")).toBe(endDate.toISOString());
    expect(getHeader(calls[0].init, "X-Api-Key")).toBe("secret-key");

    expect(response.extractionCount).toBe(42);
    expect(response.periodTokensUsed).toBe(1234);
  });

  it("deserializes unauthorized statistics responses", async () => {
    const payload = createErrorResponse("UNAUTHORIZED", false);
    const { fetchApi } = createJsonFetchMock(payload, 401);
    const api = new StatisticsApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<ErrorResponse | HTTPValidationError>(
      api.getStatisticsV1StatisticsGet(),
      401,
    );

    expect(error.data).toMatchObject({
      code: "UNAUTHORIZED",
      message: "UNAUTHORIZED message",
      correlationId: "corr-123",
      retryable: false,
    });
    expect(error.body).toEqual(payload);
  });

  it("deserializes statistics validation errors", async () => {
    const startDate = new Date("2026-04-13T10:00:00.000Z");
    const endDate = new Date("2026-04-13T11:00:00.000Z");
    const { fetchApi } = createJsonFetchMock(statisticsValidationErrorPayload, 422);
    const api = new StatisticsApi(
      new Configuration({
        basePath: "https://api.example.com",
        apiKey: "secret-key",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<HTTPValidationError>(
      api.getStatisticsV1StatisticsGet({ startDate, endDate }),
      422,
    );

    expect(error.data?.detail?.[0]?.loc).toEqual(["query", "start_date"]);
    expect(error.data?.detail?.[0]?.msg).toBe("Input should be before end_date");
  });
});
