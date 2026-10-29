import type { HTTPHeaders } from "./runtime.js";

/** Package version; tests/client-headers.test.ts keeps it equal to package.json. */
export const SDK_VERSION = "0.6.2";

/** The API labels each request by this name (scraper-api#674); `ts-sdk` is in its allowlist. */
export const SDK_USER_AGENT = `geonode-ts-sdk/${SDK_VERSION}`;

// Browsers ignore a script-set User-Agent or send it into a CORS preflight the API rejects.
const IN_BROWSER = typeof window !== "undefined" || "WorkerGlobalScope" in globalThis;

/** Adds the SDK User-Agent unless the caller set one, in any letter case. */
export function withClientHeaders(headers: HTTPHeaders): HTTPHeaders {
    if (IN_BROWSER) {
        return headers;
    }
    if (!Object.keys(headers).some((key) => key.toLowerCase() === "user-agent")) {
        headers["User-Agent"] = SDK_USER_AGENT;
    }
    return headers;
}
