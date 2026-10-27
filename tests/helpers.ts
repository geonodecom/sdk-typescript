import { expect } from "vitest";

import { ApiResponseError } from "../src/index.js";

export function createJsonFetchMock(
  payload: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  const calls: Array<{ input: string; init: RequestInit }> = [];
  const fetchApi = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input: String(input), init: init ?? {} });
    return new Response(JSON.stringify(payload), {
      status,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
    });
  };

  return { calls, fetchApi };
}

export function getHeader(init: RequestInit, key: string): string | undefined {
  const headers = (init.headers ?? {}) as Record<string, string>;
  return headers[key];
}

export async function expectApiResponseError<T>(
  promise: Promise<unknown>,
  status: number,
): Promise<ApiResponseError<T>> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiResponseError);
    const apiError = error as ApiResponseError<T>;
    expect(apiError.status).toBe(status);
    return apiError;
  }

  throw new Error(`Expected request to fail with status ${status}`);
}
