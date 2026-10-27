import { readFileSync } from "node:fs";
import { type IncomingHttpHeaders, createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { describe, expect, it } from "vitest";

import { SDK_USER_AGENT, SDK_VERSION } from "../src/clientHeaders.js";
import { Configuration, SystemApi } from "../src/index.js";
import { createJsonFetchMock, getHeader } from "./helpers.js";

const packageVersion = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf-8"),
).version;

const healthPayload = {
  version: "0.1.0",
  service: "scraper-api",
  timestamp: "2026-04-13T12:00:00.000Z",
  status: "ok",
};

describe("client identification", () => {
  it("names the SDK and the package version", () => {
    expect(SDK_VERSION).toBe(packageVersion);
    expect(SDK_USER_AGENT).toBe(`geonode-ts-sdk/${packageVersion}`);
  });

  it("sends the SDK User-Agent on every request", async () => {
    const { calls, fetchApi } = createJsonFetchMock(healthPayload);
    const api = new SystemApi(new Configuration({ basePath: "https://api.example.com", fetchApi }));

    await api.healthCheckHealthGet();

    expect(getHeader(calls[0].init, "User-Agent")).toBe(`geonode-ts-sdk/${packageVersion}`);
  });

  it("keeps a User-Agent the caller set, whatever its letter case", async () => {
    const { calls, fetchApi } = createJsonFetchMock(healthPayload);
    const api = new SystemApi(
      new Configuration({
        basePath: "https://api.example.com",
        fetchApi,
        headers: { "user-agent": "my-app/1.0" },
      }),
    );

    await api.healthCheckHealthGet();

    expect(getHeader(calls[0].init, "user-agent")).toBe("my-app/1.0");
    expect(getHeader(calls[0].init, "User-Agent")).toBeUndefined();
  });

  it("reaches the server through the runtime's own fetch", async () => {
    let received: IncomingHttpHeaders | undefined;
    const server = createServer((req, res) => {
      received = req.headers;
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(healthPayload));
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;

    try {
      const api = new SystemApi(new Configuration({ basePath: `http://127.0.0.1:${port}` }));
      await api.healthCheckHealthGet();
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }

    expect(received?.["user-agent"]).toBe(`geonode-ts-sdk/${packageVersion}`);
  });
});
