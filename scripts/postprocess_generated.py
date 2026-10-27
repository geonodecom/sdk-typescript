#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_DIR = REPO_ROOT


def apply_replacements(path: Path, replacements: list[tuple[str, str]]) -> bool:
    original = path.read_text()
    updated = original

    for old, new in replacements:
        if new in updated:
            continue
        if old not in updated:
            raise RuntimeError(f"Unable to find expected generated snippet in {path}")
        updated = updated.replace(old, new, 1)

    if updated == original:
        return False

    path.write_text(updated)
    return True


def main() -> None:
    expected_files = [
        SDK_DIR / "src/index.ts",
        SDK_DIR / "src/runtime.ts",
        SDK_DIR / "src/apis/index.ts",
        SDK_DIR / "src/models/index.ts",
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in expected_files if not path.exists()]
    if missing:
        raise SystemExit(
            "Generated TypeScript SDK is missing expected files:\n- " + "\n- ".join(missing)
        )

    changed_files: list[Path] = []

    replacement_map: dict[Path, list[tuple[str, str]]] = {
        SDK_DIR / "src/runtime.ts": [
            # Every request names this SDK (src/clientHeaders.ts, repo-owned).
            (
                "export const BASE_PATH = ",
                'import { withClientHeaders } from "./clientHeaders.js";\n\n'
                "export const BASE_PATH = ",
            ),
            (
                "        const headers = Object.assign({}, this.configuration.headers, context.headers);\n",
                "        const headers = withClientHeaders(Object.assign({}, this.configuration.headers, context.headers));\n",
            ),
            (
                '    override name: "ResponseError" = "ResponseError";\n',
                '    override name = "ResponseError";\n',
            ),
            (
                "export class FetchError extends Error {\n",
                "export class ApiResponseError<T = unknown> extends ResponseError {\n"
                '    override name = "ApiResponseError";\n'
                "    constructor(\n"
                "        response: Response,\n"
                "        public data: T | undefined,\n"
                "        public body: unknown,\n"
                "        msg?: string,\n"
                "    ) {\n"
                "        super(response, msg);\n\n"
                "        const actualProto = new.target.prototype;\n"
                "        if (Object.setPrototypeOf) {\n"
                "            Object.setPrototypeOf(this, actualProto);\n"
                "        }\n"
                "    }\n\n"
                "    get status(): number {\n"
                "        return this.response.status;\n"
                "    }\n"
                "}\n\n"
                "async function parseResponseBody(response: Response): Promise<unknown> {\n"
                "    const text = await response.text();\n"
                "    if (!text) {\n"
                "        return undefined;\n"
                "    }\n\n"
                "    try {\n"
                "        return JSON.parse(text);\n"
                "    } catch {\n"
                "        return text;\n"
                "    }\n"
                "}\n\n"
                "export async function throwApiResponseError<T>(\n"
                "    error: unknown,\n"
                "    transformers: Partial<Record<number, (json: any) => T>>,\n"
                "): Promise<never> {\n"
                "    if (!(error instanceof ResponseError)) {\n"
                "        throw error;\n"
                "    }\n\n"
                "    const body = await parseResponseBody(error.response.clone());\n"
                "    const transformer = transformers[error.response.status];\n"
                "    const data = transformer && body !== undefined ? transformer(body) : undefined;\n\n"
                "    throw new ApiResponseError(error.response, data, body, error.message);\n"
                "}\n\n"
                "export class FetchError extends Error {\n",
            ),
        ],
        SDK_DIR / "src/apis/ExtractionApi.ts": [
            (
                "    async extractV1ExtractPostRaw(requestParameters: ExtractV1ExtractPostRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<ExtractSyncResponse>> {\n",
                "    async extractV1ExtractPostRaw(requestParameters: ExtractV1ExtractPostRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<ExtractSyncResponse | ExtractAsyncResponse>> {\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => ExtractSyncResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => response.status === 202\n                ? ExtractAsyncResponseFromJSON(jsonValue)\n                : ExtractSyncResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | ExtractionErrorResponse>(error, {\n                400: ErrorResponseFromJSON,\n                401: ErrorResponseFromJSON,\n                402: ErrorResponseFromJSON,\n                422: ExtractionErrorResponseFromJSON,\n                429: ErrorResponseFromJSON,\n                500: ErrorResponseFromJSON,\n                503: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "    async extractV1ExtractPost(requestParameters: ExtractV1ExtractPostRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<ExtractSyncResponse> {\n",
                "    async extractV1ExtractPost(requestParameters: ExtractV1ExtractPostRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<ExtractSyncResponse | ExtractAsyncResponse> {\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => JobStatusResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => JobStatusResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => JobCollectionResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => JobCollectionResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/StatisticsApi.ts": [
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => StatisticsResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => StatisticsResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/SystemApi.ts": [
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => HealthResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => HealthResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<HealthResponse>(error, {\n                503: HealthResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/BatchApi.ts": [
            (
                "import type {\n  BatchAccepted,\n  BatchCancelled,\n  BatchJobsResponse,\n  BatchRequest,\n  BatchStatusResponse,\n  HTTPValidationError,\n  JobStatus,\n} from '../models/index.js';\nimport {\n    BatchAcceptedFromJSON,\n    BatchAcceptedToJSON,\n    BatchCancelledFromJSON,\n    BatchCancelledToJSON,\n    BatchJobsResponseFromJSON,\n    BatchJobsResponseToJSON,\n    BatchRequestFromJSON,\n    BatchRequestToJSON,\n    BatchStatusResponseFromJSON,\n    BatchStatusResponseToJSON,\n    HTTPValidationErrorFromJSON,\n    HTTPValidationErrorToJSON,\n    JobStatusFromJSON,\n    JobStatusToJSON,\n} from '../models/index.js';",
                "import type {\n  BatchAccepted,\n  BatchCancelled,\n  BatchJobsResponse,\n  BatchRequest,\n  BatchStatusResponse,\n  ErrorResponse,\n  HTTPValidationError,\n  JobStatus,\n} from '../models/index.js';\nimport {\n    BatchAcceptedFromJSON,\n    BatchAcceptedToJSON,\n    BatchCancelledFromJSON,\n    BatchCancelledToJSON,\n    BatchJobsResponseFromJSON,\n    BatchJobsResponseToJSON,\n    BatchRequestFromJSON,\n    BatchRequestToJSON,\n    BatchStatusResponseFromJSON,\n    BatchStatusResponseToJSON,\n    ErrorResponseFromJSON,\n    ErrorResponseToJSON,\n    HTTPValidationErrorFromJSON,\n    HTTPValidationErrorToJSON,\n    JobStatusFromJSON,\n    JobStatusToJSON,\n} from '../models/index.js';",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => BatchCancelledFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => BatchCancelledFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                409: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => BatchAcceptedFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => BatchAcceptedFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                429: ErrorResponseFromJSON,\n                503: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => BatchStatusResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => BatchStatusResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.listBatchJobsV1BatchJobsGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => BatchJobsResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.listBatchJobsV1BatchJobsGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => BatchJobsResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/CrawlApi.ts": [
            (
                "import type {\n  CrawlAccepted,\n  CrawlCancelled,\n  CrawlJobsResponse,\n  CrawlRequest,\n  CrawlStatusResponse,\n  HTTPValidationError,\n  JobStatus,\n} from '../models/index.js';\nimport {\n    CrawlAcceptedFromJSON,\n    CrawlAcceptedToJSON,\n    CrawlCancelledFromJSON,\n    CrawlCancelledToJSON,\n    CrawlJobsResponseFromJSON,\n    CrawlJobsResponseToJSON,\n    CrawlRequestFromJSON,\n    CrawlRequestToJSON,\n    CrawlStatusResponseFromJSON,\n    CrawlStatusResponseToJSON,\n    HTTPValidationErrorFromJSON,\n    HTTPValidationErrorToJSON,\n    JobStatusFromJSON,\n    JobStatusToJSON,\n} from '../models/index.js';",
                "import type {\n  CrawlAccepted,\n  CrawlCancelled,\n  CrawlJobsResponse,\n  CrawlRequest,\n  CrawlStatusResponse,\n  ErrorResponse,\n  HTTPValidationError,\n  JobStatus,\n} from '../models/index.js';\nimport {\n    CrawlAcceptedFromJSON,\n    CrawlAcceptedToJSON,\n    CrawlCancelledFromJSON,\n    CrawlCancelledToJSON,\n    CrawlJobsResponseFromJSON,\n    CrawlJobsResponseToJSON,\n    CrawlRequestFromJSON,\n    CrawlRequestToJSON,\n    CrawlStatusResponseFromJSON,\n    CrawlStatusResponseToJSON,\n    ErrorResponseFromJSON,\n    ErrorResponseToJSON,\n    HTTPValidationErrorFromJSON,\n    HTTPValidationErrorToJSON,\n    JobStatusFromJSON,\n    JobStatusToJSON,\n} from '../models/index.js';",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => CrawlCancelledFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => CrawlCancelledFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                409: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => CrawlAcceptedFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => CrawlAcceptedFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                402: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                429: ErrorResponseFromJSON,\n                503: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => CrawlStatusResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => CrawlStatusResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.listCrawlJobsV1CrawlJobsGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => CrawlJobsResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.listCrawlJobsV1CrawlJobsGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => CrawlJobsResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/MapApi.ts": [
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => MapResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => MapResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                400: ErrorResponseFromJSON,\n                401: ErrorResponseFromJSON,\n                402: ErrorResponseFromJSON,\n                408: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                429: ErrorResponseFromJSON,\n                500: ErrorResponseFromJSON,\n                503: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.getMapJobV1MapJobIdGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => MapJobDetailResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.getMapJobV1MapJobIdGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => MapJobDetailResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.listMapJobsV1MapJobsGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => MapJobsResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.listMapJobsV1MapJobsGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => MapJobsResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/SearchApi.ts": [
            (
                "        const requestOptions = await this.searchV1SearchPostRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => SearchResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.searchV1SearchPostRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => SearchResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse>(error, {\n                401: ErrorResponseFromJSON,\n                402: ErrorResponseFromJSON,\n                408: ErrorResponseFromJSON,\n                422: ErrorResponseFromJSON,\n                429: ErrorResponseFromJSON,\n                500: ErrorResponseFromJSON,\n                502: ErrorResponseFromJSON,\n                503: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.listSearchJobsV1SearchJobsGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => SearchJobsResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.listSearchJobsV1SearchJobsGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => SearchJobsResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.getSearchJobV1SearchJobIdGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => SearchJobDetailResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.getSearchJobV1SearchJobIdGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => SearchJobDetailResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/UsageApi.ts": [
            (
                "        const requestOptions = await this.getConcurrencyUsageV1UsageConcurrencyGetRequestOpts();\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => ConcurrencyUsageResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.getConcurrencyUsageV1UsageConcurrencyGetRequestOpts();\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => ConcurrencyUsageResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse>(error, {\n                401: ErrorResponseFromJSON,\n                503: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
        SDK_DIR / "src/apis/WebhooksApi.ts": [
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => WebhookCreateResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => WebhookCreateResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: ErrorResponseFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.VoidApiResponse(response);\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.VoidApiResponse(response);\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.getWebhookV1WebhooksWebhookIdGetRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => WebhookResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.getWebhookV1WebhooksWebhookIdGetRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => WebhookResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const requestOptions = await this.updateWebhookV1WebhooksWebhookIdPatchRequestOpts(requestParameters);\n        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => WebhookResponseFromJSON(jsonValue));\n",
                "        const requestOptions = await this.updateWebhookV1WebhooksWebhookIdPatchRequestOpts(requestParameters);\n        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => WebhookResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => DeliveryListResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => DeliveryListResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => WebhookListResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => WebhookListResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
            (
                "        const response = await this.request(requestOptions, initOverrides);\n\n        return new runtime.JSONApiResponse(response, (jsonValue) => RotateSecretResponseFromJSON(jsonValue));\n",
                "        try {\n            const response = await this.request(requestOptions, initOverrides);\n\n            return new runtime.JSONApiResponse(response, (jsonValue) => RotateSecretResponseFromJSON(jsonValue));\n        } catch (error) {\n            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n                401: ErrorResponseFromJSON,\n                404: ErrorResponseFromJSON,\n                422: HTTPValidationErrorFromJSON,\n                500: ErrorResponseFromJSON,\n            });\n            throw error;\n        }\n",
            ),
        ],
    }

    for path, replacements in replacement_map.items():
        if apply_replacements(path, replacements):
            changed_files.append(path)

    if changed_files:
        print("Postprocessed generated TypeScript SDK files:")
        for path in changed_files:
            print(f"- {path.relative_to(REPO_ROOT)}")
    else:
        print("Generated TypeScript SDK files already normalized.")


if __name__ == "__main__":
    main()
