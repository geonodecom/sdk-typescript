#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
from functools import partial
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_DIR = REPO_ROOT
MODELS_IMPORT = "} from '../models/index.js';"
# The request and its return as typescript-fetch writes them in a method nobody has wrapped yet.
UNWRAPPED_REQUEST = re.compile(
    r"(?P<indent> +)const response = await this\.request\(requestOptions, initOverrides\);\n\n"
    r"(?P=indent)return new runtime\.\w+ApiResponse\([^\n]*\);\n"
)
ERROR_MAPPING = re.compile(r"throwApiResponseError<[^>]*>\(error, \{\n(?P<entries>.*?)\n(?P<indent> +)\}\);", re.S)
MAPPING_ENTRY = re.compile(r"^\s*(\d{3}): (.+),$")
# Statuses whose body comes in more than one shape, so a single model would misread one of them.
ERROR_OVERRIDES = {
    # 403: ExtractionErrorResponse for Google search pages, a flat ErrorResponse when billing refuses (FORBIDDEN).
    "extractV1ExtractPost": {
        "403": "(json) => ('error' in json ? ExtractionErrorResponseFromJSON(json) : ErrorResponseFromJSON(json))",
    },
}
# typescript-fetch prefixes method names that are reserved words with an underscore.
TS_RESERVED = {"break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do", "else",
               "enum", "export", "extends", "finally", "for", "function", "if", "import", "in", "instanceof", "new",
               "return", "super", "switch", "this", "throw", "try", "typeof", "var", "void", "while", "with"}
# Set by the nightly sync: problems that would stop generation become notes for its pull request instead.
SYNC_NOTES = os.environ.get("SYNC_NOTES")


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


def _import_order(name: str) -> tuple[str, int]:
    """The generator's order: by model, then FromJSON before ToJSON (so JobStatus comes before JobStatusResponse)."""
    for rank, suffix in enumerate(("FromJSON", "ToJSON"), start=1):
        if name.endswith(suffix):
            return name[: -len(suffix)], rank
    return name, 0


def _add_sorted(text: str, opening: str, indent: str, names: list[str]) -> str:
    """Add missing names to the `opening ... } from '../models/index.js';` block; leave a complete block untouched."""
    match = re.search(re.escape(opening) + r"\n([^{}]*?)\n" + re.escape(MODELS_IMPORT), text)
    if match is None:
        raise RuntimeError(f"Unable to find the `{opening}` block of model imports")
    current = [line.strip().rstrip(",") for line in match.group(1).splitlines() if line.strip()]
    if set(names) <= set(current):
        return text
    lines = "\n".join(f"{indent}{name}," for name in sorted(set(current) | set(names), key=_import_order))
    return text[: match.start(1)] + lines + text[match.end(1) :]


def ensure_model_imports(path: Path, model: str) -> bool:
    """Import a model and its JSON helpers when the generator did not, as the error mapping below needs them."""
    original = path.read_text()
    updated = _add_sorted(original, "import type {", "  ", [model])
    updated = _add_sorted(updated, "import {", "    ", [f"{model}FromJSON", f"{model}ToJSON"])
    if updated == original:
        return False
    path.write_text(updated)
    return True


def method_name(operation_id: str) -> str:
    """The method typescript-fetch generates for an operationId: extract_v1_extract_post -> extractV1ExtractPost."""
    first, *rest = [part for part in re.split(r"[_\W]+", operation_id) if part]
    name = first[:1].lower() + first[1:] + "".join(part[:1].upper() + part[1:] for part in rest)
    return f"_{name}" if name in TS_RESERVED else name


def documented_errors(spec: dict) -> dict[str, dict[str, str | None]]:
    """Error model per documented 4xx/5xx status, by generated method.

    A status without a body gets ErrorResponse, as the hand mappings do; a body that is not a plain `$ref` gets None,
    which ensure_error_mapping refuses rather than guessing.
    """
    errors: dict[str, dict[str, str | None]] = {}
    for path, item in spec.get("paths", {}).items():
        if path.startswith("/v1/internal/"):  # filter_spec.py drops these before generation
            continue
        for operation in item.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            codes: dict[str, str | None] = {}
            for status, response in operation.get("responses", {}).items():
                if status.isdigit() and int(status) >= 400:
                    content = response.get("content")
                    ref = (content or {}).get("application/json", {}).get("schema", {}).get("$ref", "")
                    codes[status] = ref.rsplit("/", 1)[-1] if ref else (None if content else "ErrorResponse")
            if codes:
                errors[method_name(operation["operationId"])] = codes
    return errors


def ensure_error_mapping(
    path: Path, method: str, errors: dict[str, str | None], overrides: dict[str, str] | None = None
) -> bool:
    """Make `method` raise ApiResponseError for every documented status, keeping every entry already there as is."""
    text = path.read_text()
    start = text.find(f"\n    async {method}Raw(")
    if start < 0:
        raise RuntimeError(f"Unable to find {method}Raw")
    end = text.find("\n    async ", start + 1)
    end = len(text) if end < 0 else end
    body = text[start:end]

    mapping = ERROR_MAPPING.search(body)
    existing: dict[str, str] = {}
    for line in mapping.group("entries").splitlines() if mapping else []:
        entry = MAPPING_ENTRY.match(line)
        if entry is None:
            raise RuntimeError(f"Unexpected line in the error mapping of {method}Raw: {line.strip()}")
        existing[entry.group(1)] = entry.group(2)
    wanted = {**{code: f"{model}FromJSON" if model else None for code, model in errors.items()}, **(overrides or {})}
    unmappable = sorted(code for code, expr in wanted.items() if expr is None and code not in existing)
    if unmappable:
        raise RuntimeError(f"{method}Raw: status {', '.join(unmappable)} has a body schema to map by hand")
    merged = {**{code: expr for code, expr in wanted.items() if expr}, **existing}
    if mapping and merged == existing:
        return False
    models = sorted({model for expr in merged.values() for model in re.findall(r"(\w+)FromJSON", expr)})

    def mapping_block(closing_indent: str) -> str:
        lines = "".join(f"{closing_indent}    {code}: {expr},\n" for code, expr in sorted(merged.items()))
        return f"throwApiResponseError<{' | '.join(models)}>(error, {{\n{lines}{closing_indent}}});"

    if mapping:
        body = body[: mapping.start()] + mapping_block(mapping.group("indent")) + body[mapping.end() :]
    else:
        request = UNWRAPPED_REQUEST.search(body)
        if request is None:
            raise RuntimeError(f"Unable to find the request in {method}Raw")
        indent = request.group("indent")
        call = "".join(f"    {line}\n" if line else "\n" for line in request.group(0).rstrip("\n").split("\n"))
        wrapped = (f"{indent}try {{\n{call}{indent}}} catch (error) {{\n"
                   f"{indent}    await runtime.{mapping_block(indent + '    ')}\n"
                   f"{indent}    throw error;\n{indent}}}\n")
        body = body[: request.start()] + wrapped + body[request.end() :]
    text = text[:start] + body + text[end:]
    for model in models:
        text = _add_sorted(text, "import type {", "  ", [model])
        text = _add_sorted(text, "import {", "    ", [f"{model}FromJSON", f"{model}ToJSON"])
    path.write_text(text)
    return True


def unwrapped_methods(path: Path) -> list[str]:
    """Request methods that throw the generator's plain ResponseError instead of the documented ApiResponseError."""
    parts = re.split(r"\n    async (\w+Raw)\(", path.read_text())
    return [name for name, body in zip(parts[1::2], parts[2::2], strict=True) if "throwApiResponseError" not in body]


def normalize_whitespace(path: Path) -> bool:
    """Drop trailing spaces and end the file with exactly one newline, as the committed sources do."""
    original = path.read_text()
    updated = "\n".join(line.rstrip(" \t") for line in original.split("\n")).rstrip("\n") + "\n"
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

    notes: list[str] = []

    def problem(message: str) -> None:
        if not SYNC_NOTES:
            raise RuntimeError(message)
        print(f"WARNING: {message}")
        notes.append(message)

    def run(path: Path, edit: Callable[[], bool]) -> None:
        relative = path.relative_to(REPO_ROOT)
        if not path.exists():
            problem(f"`{relative}` is no longer generated; remove its edits from scripts/postprocess_generated.py.")
            return
        try:
            if edit() and path not in changed_files:
                changed_files.append(path)
        except RuntimeError as exc:
            problem(f"`{relative}`: {exc}; the generated code changed, update scripts/postprocess_generated.py.")

    # The error mappings below use ErrorResponse; newer specs import it already, older ones did not.
    for name in ("BatchApi", "CrawlApi"):
        path = SDK_DIR / f"src/apis/{name}.ts"
        run(path, partial(ensure_model_imports, path, "ErrorResponse"))

    for path, replacements in replacement_map.items():
        run(path, partial(apply_replacements, path, replacements))

    # Every documented error status raises ApiResponseError, so new endpoints and status codes need no hand edits.
    errors = documented_errors(json.loads((REPO_ROOT / "openapi.json").read_text()))
    api_files = sorted((SDK_DIR / "src/apis").glob("*Api.ts"))
    generated: set[str] = set()
    for path in api_files:
        for method in re.findall(r"\n    async (\w+)Raw\(", path.read_text()):
            generated.add(method)
            if method in errors:
                run(path, partial(ensure_error_mapping, path, method, errors[method], ERROR_OVERRIDES.get(method)))
    if missing := sorted(set(errors) - generated):
        message = ("No generated method found for these operations, so their errors are not mapped; check "
                   "method_name in scripts/postprocess_generated.py: " + ", ".join(f"`{m}`" for m in missing) + ".")
        print(f"WARNING: {message}")
        notes.append(message)

    unwrapped = [f"{p.stem}.{m}" for p in api_files for m in unwrapped_methods(p)]
    if unwrapped:
        names = ", ".join(f"`{m}`" for m in unwrapped)
        message = ("These methods throw a plain ResponseError, not the documented ApiResponseError; add them to "
                   f"the error mappings in scripts/postprocess_generated.py: {names}.")
        print(f"WARNING: {message}")
        notes.append(message)

    # The generator leaves trailing spaces and blank lines; trimming them keeps regeneration diffs to real changes.
    trimmed = sum(normalize_whitespace(path) for path in sorted((SDK_DIR / "src").rglob("*.ts")))
    if trimmed:
        print(f"Trimmed trailing whitespace in {trimmed} generated files.")

    if changed_files:
        print("Postprocessed generated TypeScript SDK files:")
        for path in changed_files:
            print(f"- {path.relative_to(REPO_ROOT)}")
    else:
        print("Generated TypeScript SDK files already normalized.")

    if SYNC_NOTES and notes:
        with open(SYNC_NOTES, "a", encoding="utf-8") as fh:
            fh.writelines(f"- {note}\n" for note in notes)


if __name__ == "__main__":
    main()
