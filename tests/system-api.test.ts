import { describe, expect, it } from "vitest";

import { Configuration, type HealthResponse, HealthStatus, SystemApi } from "../src/index.js";
import { createJsonFetchMock, expectApiResponseError, getHeader } from "./helpers.js";

const healthPayload = {
  version: "0.1.0",
  service: "scraper-api",
  timestamp: "2026-04-13T12:00:00.000Z",
  status: "ok",
};

describe("SystemApi", () => {
  it("deserializes health responses and does not require auth", async () => {
    const { calls, fetchApi } = createJsonFetchMock(healthPayload);

    const api = new SystemApi(
      new Configuration({
        basePath: "https://api.example.com",
        fetchApi,
      }),
    );

    const response = await api.healthCheckHealthGet();

    expect(calls).toHaveLength(1);
    expect(calls[0].input).toBe("https://api.example.com/health");
    expect(getHeader(calls[0].init, "X-Api-Key")).toBeUndefined();
    expect(response.service).toBe("scraper-api");
    expect(response.timestamp).toBeInstanceOf(Date);
  });

  it("deserializes degraded 503 health payloads on API errors", async () => {
    const degradedPayload = { ...healthPayload, status: "degraded" };
    const { fetchApi } = createJsonFetchMock(degradedPayload, 503);
    const api = new SystemApi(
      new Configuration({
        basePath: "https://api.example.com",
        fetchApi,
      }),
    );

    const error = await expectApiResponseError<HealthResponse>(api.healthCheckHealthGet(), 503);

    expect(error.data?.status).toBe(HealthStatus.Degraded);
    expect(error.data?.service).toBe("scraper-api");
    expect(error.body).toEqual(degradedPayload);
  });
});
