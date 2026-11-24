import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "sync_openapi.py"


@pytest.fixture(scope="module")
def sync():
    spec = importlib.util.spec_from_file_location("sync_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses look the defining module up in sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def make_spec(paths, schemas=None):
    return {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "paths": paths,
            "components": {"schemas": schemas or {}}}


def jobs_list(*params):
    return {"get": {"parameters": [{"name": p, "in": "query"} for p in params], "responses": {"200": {}}}}


OLD = make_spec(
    {"/v1/extract/jobs": jobs_list("job_id", "url"), "/v1/extract": {"post": {"responses": {"200": {}}}}},
    {"ErrorCode": {"enum": ["TIMEOUT"]}, "Job": {"properties": {"id": {}, "url": {}}}, "Gone": {}},
)
NEW = make_spec(
    {
        "/v1/extract/jobs": jobs_list("job_id"),
        "/v1/extract": {"post": {"responses": {"200": {}, "403": {}}}},
        "/v1/google/search/light": {"post": {"responses": {"200": {}}}},
    },
    {"ErrorCode": {"enum": ["TIMEOUT", "TARGET_BLOCKED"]}, "Job": {"properties": {"id": {}, "status": {}}}},
)


def test_compare_lists_what_an_sdk_user_would_notice(sync):
    diff = sync.compare(OLD, NEW)

    assert diff.added_operations == ["`POST /v1/google/search/light`"]
    assert diff.removed_operations == []
    assert diff.removed_parameters == ["`url` on `GET /v1/extract/jobs`"]
    assert diff.added_responses == ["`403` on `POST /v1/extract`"]
    assert diff.removed_schemas == ["`Gone`"]
    assert diff.added_fields == ["`Job.status`"]
    assert diff.removed_fields == ["`Job.url`"]
    assert diff.added_enum_values == ["`TARGET_BLOCKED` in `ErrorCode`"]


def test_compare_of_identical_specs_is_empty(sync):
    assert sync.compare(OLD, OLD).is_empty()


def test_compare_sees_enum_values_inside_an_optional_field(sync):
    def search(*engines):
        engine = {"anyOf": [{"enum": list(engines), "type": "string"}, {"type": "null"}]}
        return make_spec({}, {"SearchRequest": {"properties": {"engine": engine}}})

    diff = sync.compare(search("brave", "naver"), search("yahoo", "naver"))

    assert diff.added_enum_values == ["`yahoo` in `SearchRequest.engine`"]
    assert diff.removed_enum_values == ["`brave` in `SearchRequest.engine`"]


def test_compare_lists_fields_that_changed_required(sync):
    before = make_spec({}, {"Job": {"properties": {"id": {}, "url": {}}, "required": ["id"]}})
    after = make_spec({}, {"Job": {"properties": {"id": {}, "url": {}}, "required": ["url"]}})

    diff = sync.compare(before, after)

    assert diff.newly_required == ["`Job.url`"]
    assert diff.no_longer_required == ["`Job.id`"]


def test_changelog_entry_leaves_response_codes_to_the_pull_request(sync):
    entry = sync.changelog_entry(sync.compare(OLD, NEW))

    assert entry[0] == "- Synced with the production API spec."
    assert "  - Removed request parameters: `url` on `GET /v1/extract/jobs`." in entry
    assert not any("403" in line for line in entry)


@pytest.mark.parametrize(
    ("unreleased", "expected"),
    [
        ("## [Unreleased]\n\n## [0.6.2] - 2026-10-28\n", "## [Unreleased]\n\n- new\n\n## [0.6.2] - 2026-10-28\n"),
        ("## [Unreleased]\n\n- old\n\n## [0.6.2]\n", "## [Unreleased]\n\n- new\n- old\n\n## [0.6.2]\n"),
        ("## [Unreleased]\n", "## [Unreleased]\n\n- new\n"),
    ],
)
def test_changelog_entry_goes_first_under_unreleased(sync, unreleased, expected):
    assert sync.add_changelog_entry("# Changelog\n\n" + unreleased, ["- new"]) == "# Changelog\n\n" + expected


def test_changelog_without_unreleased_heading_is_refused(sync):
    with pytest.raises(SystemExit):
        sync.add_changelog_entry("# Changelog\n\n## [0.6.2]\n", ["- new"])


def test_spec_that_lost_most_paths_is_refused(sync):
    with pytest.raises(SystemExit, match="refusing"):
        sync.check_plausible(NEW, make_spec({"/health": {"get": {}}}))


@pytest.fixture
def repo(sync, tmp_path, monkeypatch):
    spec_file, changelog = tmp_path / "openapi.json", tmp_path / "CHANGELOG.md"
    spec_file.write_text(sync.dump(OLD), encoding="utf-8")
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [0.6.2]\n", encoding="utf-8")
    monkeypatch.setattr(sync, "SPEC_FILE", spec_file)
    monkeypatch.setattr(sync, "CHANGELOG_FILE", changelog)
    monkeypatch.setattr(sync, "load_filter", lambda: lambda spec: spec)
    return tmp_path


def test_main_leaves_files_alone_when_nothing_changed(sync, repo, capsys):
    (repo / "source.json").write_text(json.dumps(OLD), encoding="utf-8")
    before = (repo / "CHANGELOG.md").read_text(encoding="utf-8")

    assert sync.main(["--source", str(repo / "source.json")]) == 0

    assert capsys.readouterr().out.strip().splitlines()[-1] == "changed=false"
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == before


def test_main_rewrites_spec_changelog_and_summary(sync, repo, capsys):
    (repo / "source.json").write_text(json.dumps(NEW), encoding="utf-8")

    sync.main(["--source", str(repo / "source.json"), "--summary", str(repo / "summary.md"), "--date", "2026-11-24"])

    assert capsys.readouterr().out.strip().splitlines()[-1] == "changed=true"
    assert json.loads((repo / "openapi.json").read_text(encoding="utf-8")) == NEW
    assert "- Synced with the production API spec." in (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "| New endpoints | `POST /v1/google/search/light` |" in (repo / "summary.md").read_text(encoding="utf-8")


def test_main_keeps_the_servers_this_repo_sets(sync, repo):
    servers = [{"url": "https://scraper.geonode.io", "description": "Production"}]
    (repo / "openapi.json").write_text(sync.dump({**OLD, "servers": servers}), encoding="utf-8")
    (repo / "source.json").write_text(json.dumps(NEW), encoding="utf-8")

    sync.main(["--source", str(repo / "source.json")])

    assert json.loads((repo / "openapi.json").read_text(encoding="utf-8"))["servers"] == servers


def test_main_writes_nothing_when_the_changelog_has_no_unreleased_heading(sync, repo):
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.6.2]\n", encoding="utf-8")
    (repo / "source.json").write_text(json.dumps(NEW), encoding="utf-8")
    spec_before = (repo / "openapi.json").read_text(encoding="utf-8")

    with pytest.raises(SystemExit):
        sync.main(["--source", str(repo / "source.json")])

    assert (repo / "openapi.json").read_text(encoding="utf-8") == spec_before
