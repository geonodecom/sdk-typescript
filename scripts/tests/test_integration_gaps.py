import importlib.util
import json
import sys
from pathlib import Path

import pytest

# The same test file lives in sdk-python (tests/) and sdk-typescript (scripts/tests/).
REPO = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "integration_gaps.py").is_file())
SCRIPT = REPO / "scripts" / "integration_gaps.py"


@pytest.fixture(scope="module")
def gaps():
    spec = importlib.util.spec_from_file_location("integration_gaps", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def op(*params, body=None):
    operation = {"parameters": [{"name": p, "in": "query", "schema": {"type": "string"}} for p in params]}
    if body:
        operation["requestBody"] = {
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{body}"}}}
        }
    return operation


def spec(engines, paths):
    return {
        "openapi": "3.1.0",
        "paths": paths,
        "components": {
            "schemas": {
                "SearchRequest": {"properties": {"query": {"type": "string"}, "engine": {"enum": engines}}},
                "LightRequest": {"properties": {"device": {"enum": ["desktop", "mobile"]}}},
            }
        },
    }


BEFORE = spec(
    ["brave", "duckduckgo"],
    {
        "/health": {"get": op()},
        "/v1/extract": {"post": op()},
        "/v1/extract/jobs": {"get": op("url", "status")},
        "/v1/search": {"post": op(body="SearchRequest")},
        "/v1/search/jobs": {"get": op("query", "status")},
        "/v1/crawl/{job_id}": {"get": op(), "delete": op()},
        "/v1/batch/jobs": {"get": op()},
        "/v1/map/jobs": {"get": op()},
        "/v1/internal/statistics": {"get": op()},
    },
)
AFTER = spec(
    ["duckduckgo", "yahoo"],
    {
        **BEFORE["paths"],
        "/v1/extract/jobs": {"get": op("status")},
        "/v1/search/jobs": {"get": op("status")},
        "/v1/google/search/light": {"post": op(body="LightRequest")},
    },
)


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")


@pytest.fixture
def sources(tmp_path):
    write(tmp_path / "integration-make", {"base.imljson": json.dumps({"baseUrl": "https://scraper.geonode.io/v1"})})
    # Make files may start with a byte order mark.
    (tmp_path / "integration-make/modules/list/api.imljson").parent.mkdir(parents=True)
    (tmp_path / "integration-make/modules/list/api.imljson").write_text(
        "﻿" + json.dumps({"url": "/extract/jobs", "method": "GET", "qs": {"url": "{{parameters.url}}"}}),
        encoding="utf-8",
    )
    write(tmp_path / "integration-make", {"modules/raw/api.imljson": json.dumps({"url": "{{parameters.url}}"})})
    write(
        tmp_path / "integration-n8n",
        {
            "nodes/Api/Api.node.ts": (
                "await request.call(this, { method: 'POST', url: '/v1/extract', body });\n"
                "const jobUrl = `/v1/crawl/${jobId}`;\n"
                "return request.call(this, { method: 'GET', url: '/v1/search/jobs', qs });\n"
            ),
            "nodes/Api/descriptions/SearchDescription.ts": (
                "{ displayName: 'Query', name: 'query', type: 'string' },\n{ name: 'Brave', value: 'brave' },\n"
            ),
        },
    )
    write(
        tmp_path / "integration-zapier",
        {
            "triggers/job_completed.js": (
                "const EVENTS = { extract_completed: 'extract', batch_completed: 'batch' };\n"
                "await request(z, bundle, { method: 'GET', path: `/v1/${jobType}/jobs` });\n"
            ),
            "creates/extract_url.js": (
                "{ key: 'url', label: 'URL' }\nrequest(z, b, { method: 'POST', path: '/v1/extract' });\n"
            ),
            "lib/samples.js": "module.exports = { url: '/v1/map/jobs' };\n",
        },
    )
    return tmp_path


@pytest.fixture
def usages(gaps, sources):
    return gaps.read_integrations(sources, {"extract", "search", "crawl", "batch", "map", "google"})


def test_make_is_read_from_its_module_definitions(usages):
    make = usages["Make"]

    assert make.calls == {("GET", "/v1/extract/jobs")}  # the raw "make an API call" module is not coverage
    assert make.query["GET /v1/extract/jobs"] == {"url"}


def test_code_integrations_count_status_urls_as_gets_and_expand_named_job_types(usages):
    n8n, zapier = usages["n8n"], usages["Zapier"]

    assert n8n.calls_op("GET", "/v1/crawl/{job_id}") and not n8n.calls_op("DELETE", "/v1/crawl/{job_id}")
    assert zapier.calls_op("GET", "/v1/extract/jobs") and zapier.calls_op("GET", "/v1/batch/jobs")
    assert not zapier.calls_op("GET", "/v1/map/jobs")  # not a job type in that file, and samples are skipped


def test_report_lists_what_the_sync_removes_and_adds(gaps, usages):
    text = gaps.report(AFTER, usages, BEFORE)
    removed = text.split("**Removed by this sync and still used**")[1].split("**New in this sync**")[0]

    assert "`GET /v1/extract/jobs` no longer takes `url`: Make still sends it." in removed
    assert "Zapier" not in removed  # its `url` field belongs to the extract form, not to the job list
    assert "`GET /v1/search/jobs` no longer takes `query`: n8n may still send it" in removed
    assert "`brave` is no longer allowed in `SearchRequest.engine`: n8n still offers it." in removed
    assert "| `POST /v1/google/search/light` | — | — | — |" in text
    assert "| `yahoo` in `SearchRequest.engine` | — | — | — |" in text
    assert "desktop" not in text  # values of a new endpoint's own fields come with its row
    assert "/health" not in text and "/internal/" not in text
    assert "<details><summary>Every endpoint (n8n 3 of " in text


def test_an_integration_that_cannot_be_read_is_named_and_marked_unknown(gaps, sources):
    import shutil

    shutil.rmtree(sources / "integration-zapier")
    usages = gaps.read_integrations(sources, {"extract"})
    text = gaps.report(AFTER, usages, BEFORE)

    assert "**Could not read:** Zapier (not cloned)." in text
    assert "| `POST /v1/extract` | ✓ | — | ? |" in text


def test_a_layout_change_that_finds_no_calls_is_reported(gaps, sources):
    for file in (sources / "integration-n8n").rglob("*.ts"):
        file.write_text("// moved elsewhere\n", encoding="utf-8")

    usages = gaps.read_integrations(sources, {"extract"})

    assert usages["n8n"].error == "no API calls found; its layout may have changed"


def test_without_a_previous_spec_it_shows_todays_coverage(gaps, usages):
    text = gaps.report(AFTER, usages)

    assert "**Removed by this sync" not in text and "<details>" not in text
    assert text.count("| `") == len(gaps.operations(AFTER))


def test_main_writes_the_section(gaps, sources, tmp_path):
    (tmp_path / "before.json").write_text(json.dumps(BEFORE), encoding="utf-8")
    (tmp_path / "after.json").write_text(json.dumps(AFTER), encoding="utf-8")
    out = tmp_path / "integrations.md"

    gaps.main(["--before", str(tmp_path / "before.json"), "--after", str(tmp_path / "after.json"),
               "--sources", str(sources), "--out", str(out)])  # fmt: skip

    assert out.read_text(encoding="utf-8").startswith("## Integrations: n8n, Make, Zapier")


def test_a_renamed_placeholder_is_not_a_removal(gaps, usages):
    after = json.loads(json.dumps(AFTER))
    after["paths"]["/v1/crawl/{crawl_id}"] = after["paths"].pop("/v1/crawl/{job_id}")

    text = gaps.report(after, usages, BEFORE)

    assert "is gone" not in text
    assert "`GET /v1/crawl/{crawl_id}`" in text


def test_a_path_inside_a_request_object_takes_only_its_method(gaps, tmp_path):
    write(
        tmp_path / "integration-zapier",
        {
            "triggers/hook.js": (
                "await request(z, bundle, { method: 'POST', path: '/v1/webhooks' });\n"
                "await request(z, bundle, { path: `/v1/webhooks/${id}`, method: 'DELETE' });\n"
            )
        },
    )

    zapier = gaps.read_integrations(tmp_path, {"webhooks"})["Zapier"]

    assert zapier.calls == {("POST", "/v1/webhooks"), ("DELETE", "/v1/webhooks/{}")}


def test_a_removed_resource_still_expands_a_job_type_variable(gaps, sources, tmp_path):
    after = json.loads(json.dumps(AFTER))
    del after["paths"]["/v1/batch/jobs"]
    (tmp_path / "before.json").write_text(json.dumps(BEFORE), encoding="utf-8")
    (tmp_path / "after.json").write_text(json.dumps(after), encoding="utf-8")
    out = tmp_path / "out.md"

    gaps.main(["--before", str(tmp_path / "before.json"), "--after", str(tmp_path / "after.json"),
               "--sources", str(sources), "--out", str(out)])  # fmt: skip

    assert "- `GET /v1/batch/jobs` is gone: Zapier still calls it." in out.read_text(encoding="utf-8")


def test_spec_walk_follows_refs_without_looping(gaps):
    spec = {
        "paths": {
            "/v1/things": {
                "parameters": [{"$ref": "#/components/parameters/Url"}],
                "get": {
                    "parameters": [{"name": "status", "in": "query", "schema": {"$ref": "#/components/schemas/S"}}]
                },
                "post": op(body="Node"),
            }
        },
        "components": {
            "parameters": {"Url": {"name": "url", "in": "query", "schema": {"type": "string"}}},
            "schemas": {
                "S": {"enum": ["a", "b"]},
                "Node": {
                    "allOf": [{"properties": {"kind": {"enum": ["x"]}, "child": {"$ref": "#/components/schemas/Node"}}}]
                },
            },
        },
    }

    assert gaps.query_params(spec, "/v1/things", "GET") == {"url", "status"}
    assert gaps.request_enums(spec) == {"S": {"a", "b"}, "Node.kind": {"x"}}


def test_make_query_includes_pagination(gaps, tmp_path):
    write(
        tmp_path / "integration-make",
        {
            "base.imljson": json.dumps({"baseUrl": "https://scraper.geonode.io/v1"}),
            "modules/jobs/api.imljson": json.dumps(
                {"url": "/batch/jobs", "qs": {"status": "x"}, "pagination": {"qs": {"page": "{{pagination.page}}"}}}
            ),
        },
    )

    make = gaps.read_integrations(tmp_path, set())["Make"]

    assert make.query["GET /v1/batch/jobs"] == {"status", "page"}


def test_status_url_keys_are_not_request_urls(gaps, tmp_path):
    write(tmp_path / "integration-n8n", {"nodes/A.node.ts": "return { status_url: '/v1/batch/x', method: 'POST' };\n"})

    n8n = gaps.read_integrations(tmp_path, {"batch"})["n8n"]

    assert n8n.calls == {("GET", "/v1/batch/x")}


def test_enum_walk_reads_path_level_query_parameters(gaps):
    spec = {
        "paths": {
            "/v1/things": {"parameters": [{"name": "kind", "in": "query", "schema": {"enum": ["a"]}}], "get": op()}
        },
        "components": {"schemas": {}},
    }

    assert gaps.request_enums(spec) == {"GET /v1/things ?kind": {"a"}}
