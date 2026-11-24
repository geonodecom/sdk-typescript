import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "postprocess_generated.py"

VALUE_IMPORTS = (
    "import {\n"
    "    JobStatusFromJSON,\n"
    "    JobStatusToJSON,\n"
    "    JobStatusResponseFromJSON,\n"
    "    JobStatusResponseToJSON,\n"
    "} from '../models/index.js';\n"
)


@pytest.fixture
def pp():
    spec = importlib.util.spec_from_file_location("postprocess_generated", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def test_a_complete_import_block_is_left_alone(pp):
    assert pp._add_sorted(VALUE_IMPORTS, "import {", "    ", ["JobStatusFromJSON"]) == VALUE_IMPORTS


def test_missing_imports_go_in_the_generators_order(pp):
    updated = pp._add_sorted(VALUE_IMPORTS, "import {", "    ", ["ErrorResponseFromJSON", "ErrorResponseToJSON"])

    names = [line.strip(" ,") for line in updated.splitlines()[1:-1]]
    assert names == ["ErrorResponseFromJSON", "ErrorResponseToJSON", "JobStatusFromJSON", "JobStatusToJSON",
                     "JobStatusResponseFromJSON", "JobStatusResponseToJSON"]


def test_normalize_whitespace_trims_line_ends_and_trailing_blank_lines(pp, tmp_path):
    path = tmp_path / "Model.ts"
    path.write_text("/**\n * \n */\nexport {};\n\n\n")

    assert pp.normalize_whitespace(path)
    assert path.read_text() == "/**\n *\n */\nexport {};\n"
    assert not pp.normalize_whitespace(path)


def test_unwrapped_methods_lists_requests_without_the_error_mapping(pp, tmp_path):
    path = tmp_path / "GoogleApi.ts"
    path.write_text(
        "export class GoogleApi {\n"
        "    async searchRaw(requestParameters) {\n"
        "        try { await this.request(o); } catch (error) { await runtime.throwApiResponseError(error, {}); }\n"
        "    }\n"
        "    async shoppingRaw(requestParameters) {\n"
        "        const response = await this.request(o);\n"
        "    }\n"
        "}\n"
    )

    assert pp.unwrapped_methods(path) == ["shoppingRaw"]


def test_method_name_follows_typescript_fetch(pp):
    assert pp.method_name("extract_v1_extract_post") == "extractV1ExtractPost"
    assert pp.method_name("get_job_result_v1_extract__job_id__get") == "getJobResultV1ExtractJobIdGet"
    assert pp.method_name("Get_Thing") == "getThing"
    assert pp.method_name("delete") == "_delete"


def test_documented_errors_reads_4xx_and_5xx_with_their_models(pp):
    validation = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}}}
    either = {"content": {"application/json": {"schema": {"anyOf": [{"$ref": "#/a"}, {"$ref": "#/b"}]}}}}
    spec = {"paths": {
        "/v1/x": {"post": {"operationId": "x_v1_x_post",
                           "responses": {"200": {}, "202": {}, "401": {}, "403": either, "422": validation}}},
        "/v1/internal/y": {"get": {"operationId": "y_get", "responses": {"500": {}}}},
    }}

    assert pp.documented_errors(spec) == {
        "xV1XPost": {"401": "ErrorResponse", "403": None, "422": "HTTPValidationError"},
    }


def test_repo_maps_every_documented_error_status(pp):
    root = SCRIPT.parents[1]
    errors = pp.documented_errors(json.loads((root / "openapi.json").read_text()))
    missing = []
    for path in sorted((root / "src" / "apis").glob("*Api.ts")):
        text = path.read_text()
        for method in re.findall(r"\n    async (\w+)Raw\(", text):
            body = text.split(f"\n    async {method}Raw(", 1)[1].split("\n    async ", 1)[0]
            mapped = set(re.findall(r"^\s*(\d{3}): ", body, re.M))
            missing += [f"{path.stem}.{method} {code}" for code in errors.get(method, {}) if code not in mapped]

    assert missing == []


API_FILE = (
    "import type {\n  ErrorResponse,\n  ThingResponse,\n} from '../models/index.js';\n"
    "import {\n    ErrorResponseFromJSON,\n    ErrorResponseToJSON,\n    ThingResponseFromJSON,\n"
    "    ThingResponseToJSON,\n} from '../models/index.js';\n\n"
    "export class ThingApi {\n"
    "    async getThingRaw(initOverrides?: RequestInit): Promise<runtime.ApiResponse<ThingResponse>> {\n"
    "        const requestOptions = await this.getThingRequestOpts();\n"
    "        const response = await this.request(requestOptions, initOverrides);\n\n"
    "        return new runtime.JSONApiResponse(response, (jsonValue) => ThingResponseFromJSON(jsonValue));\n"
    "    }\n"
    "}\n"
)


def test_ensure_error_mapping_wraps_a_method_the_generator_left_bare(pp, tmp_path):
    path = tmp_path / "ThingApi.ts"
    path.write_text(API_FILE)

    assert pp.ensure_error_mapping(path, "getThing", {"503": "ErrorResponse", "422": "HTTPValidationError"})

    text = path.read_text()
    assert (
        "        try {\n"
        "            const response = await this.request(requestOptions, initOverrides);\n\n"
        "            return new runtime.JSONApiResponse(response, (jsonValue) => ThingResponseFromJSON(jsonValue));\n"
        "        } catch (error) {\n"
        "            await runtime.throwApiResponseError<ErrorResponse | HTTPValidationError>(error, {\n"
        "                422: HTTPValidationErrorFromJSON,\n"
        "                503: ErrorResponseFromJSON,\n"
        "            });\n"
        "            throw error;\n"
        "        }\n"
    ) in text
    assert "  HTTPValidationError,\n" in text and "    HTTPValidationErrorFromJSON,\n" in text
    assert pp.unwrapped_methods(path) == []
    assert not pp.ensure_error_mapping(path, "getThing", {"503": "ErrorResponse", "422": "HTTPValidationError"})


def test_ensure_error_mapping_keeps_hand_entries_verbatim_and_applies_overrides(pp, tmp_path):
    path = tmp_path / "ThingApi.ts"
    path.write_text(API_FILE)
    pp.ensure_error_mapping(path, "getThing", {}, {"409": "(json) => ErrorResponseFromJSON(json)"})

    pp.ensure_error_mapping(path, "getThing", {"409": "ThingResponse", "503": "ErrorResponse"},
                            {"403": "(json) => ('error' in json ? ErrorResponseFromJSON(json) : json)"})

    text = path.read_text()
    assert "403: (json) => ('error' in json ? ErrorResponseFromJSON(json) : json)," in text
    assert "409: (json) => ErrorResponseFromJSON(json)," in text
    assert "503: ErrorResponseFromJSON," in text


def test_ensure_error_mapping_refuses_a_schema_it_cannot_read(pp, tmp_path):
    path = tmp_path / "ThingApi.ts"
    path.write_text(API_FILE)

    with pytest.raises(RuntimeError, match="status 403"):
        pp.ensure_error_mapping(path, "getThing", {"403": None})


def test_ensure_error_mapping_adds_codes_but_keeps_a_hand_chosen_model(pp, tmp_path):
    path = tmp_path / "ThingApi.ts"
    path.write_text(API_FILE)
    pp.ensure_error_mapping(path, "getThing", {"422": "ErrorResponse"})

    assert pp.ensure_error_mapping(path, "getThing", {"403": "ErrorResponse", "422": "HTTPValidationError"})

    text = path.read_text()
    assert "403: ErrorResponseFromJSON,\n                422: ErrorResponseFromJSON," in text


@pytest.fixture
def bare_tree(pp, tmp_path, monkeypatch):
    for name in ("src/index.ts", "src/runtime.ts", "src/apis/index.ts", "src/models/index.ts"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("export {};\n")
    (tmp_path / "openapi.json").write_text('{"paths": {}}\n')
    monkeypatch.setattr(pp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pp, "SDK_DIR", tmp_path)
    return tmp_path


def test_without_sync_notes_a_missing_api_file_is_an_error(pp, bare_tree, monkeypatch):
    monkeypatch.setattr(pp, "SYNC_NOTES", None)

    with pytest.raises(RuntimeError):
        pp.main()


def test_with_sync_notes_problems_become_notes(pp, bare_tree, monkeypatch):
    notes = bare_tree / "notes.md"
    monkeypatch.setattr(pp, "SYNC_NOTES", str(notes))

    pp.main()

    text = notes.read_text()
    assert "`src/apis/BatchApi.ts` is no longer generated" in text
    assert "`src/runtime.ts`: Unable to find expected generated snippet" in text
