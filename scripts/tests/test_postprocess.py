import importlib.util
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


@pytest.fixture
def bare_tree(pp, tmp_path, monkeypatch):
    for name in ("src/index.ts", "src/runtime.ts", "src/apis/index.ts", "src/models/index.ts"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("export {};\n")
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
