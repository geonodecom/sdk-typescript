import importlib.util
import json
import sys
from pathlib import Path

import pytest

# The same test file lives in sdk-python (tests/) and sdk-typescript (scripts/tests/).
REPO = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "release.py").is_file())
SCRIPT = REPO / "scripts" / "release.py"

CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n- New thing.\n\n## [0.6.2] - 2026-10-28\n\n- Old thing.\n"


@pytest.fixture(scope="module")
def release():
    spec = importlib.util.spec_from_file_location("release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


@pytest.fixture(autouse=True)
def no_actions_output(monkeypatch):
    # CI sets GITHUB_OUTPUT for every step; the tests must not write into the real one.
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


def write(root, files):
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")


@pytest.fixture
def python_sdk(tmp_path):
    write(tmp_path, {
        "pyproject.toml": '[project]\nname = "geonode-scraper-sdk"\nversion = "0.6.2"\n',
        "geonode_scraper_sdk/__init__.py": '__version__ = "0.6.2"\n',
        "geonode_scraper_sdk/api_client.py": "        self.user_agent = 'geonode-python-sdk/0.6.2'\n",
        "geonode_scraper_sdk/configuration.py": '               "SDK Package Version: 0.6.2".\\\n',
        "CHANGELOG.md": CHANGELOG,
    })
    return tmp_path


@pytest.fixture
def typescript_sdk(tmp_path):
    lock = {"name": "sdk", "version": "0.6.2", "lockfileVersion": 3,
            "packages": {"": {"name": "sdk", "version": "0.6.2"}, "node_modules/x": {"version": "0.6.2"}}}
    write(tmp_path, {
        "package.json": '{\n  "name": "sdk",\n  "version": "0.6.2",\n  "files": ["dist"]\n}\n',
        "package-lock.json": json.dumps(lock, indent=2) + "\n",
        "src/clientHeaders.ts": 'export const SDK_VERSION = "0.6.2";\n',
        "CHANGELOG.md": CHANGELOG,
    })
    return tmp_path


def test_python_release_sets_every_version_and_dates_the_notes(release, python_sdk):
    release.main(["minor", "--date", "2026-11-25", "--root", str(python_sdk)])

    assert 'version = "0.7.0"' in (python_sdk / "pyproject.toml").read_text()
    assert '__version__ = "0.7.0"' in (python_sdk / "geonode_scraper_sdk/__init__.py").read_text()
    assert "'geonode-python-sdk/0.7.0'" in (python_sdk / "geonode_scraper_sdk/api_client.py").read_text()
    assert '"SDK Package Version: 0.7.0"' in (python_sdk / "geonode_scraper_sdk/configuration.py").read_text()
    assert (python_sdk / "CHANGELOG.md").read_text() == (
        "# Changelog\n\n## [Unreleased]\n\n## [0.7.0] - 2026-11-25\n\n- New thing.\n\n"
        "## [0.6.2] - 2026-10-28\n\n- Old thing.\n"
    )


def test_typescript_release_touches_only_the_package_versions(release, typescript_sdk):
    release.main(["0.7.0", "--date", "2026-11-25", "--root", str(typescript_sdk)])

    assert (typescript_sdk / "package.json").read_text() == (
        '{\n  "name": "sdk",\n  "version": "0.7.0",\n  "files": ["dist"]\n}\n'
    )
    lock = json.loads((typescript_sdk / "package-lock.json").read_text())
    assert (lock["version"], lock["packages"][""]["version"]) == ("0.7.0", "0.7.0")
    assert lock["packages"]["node_modules/x"]["version"] == "0.6.2"
    assert 'SDK_VERSION = "0.7.0"' in (typescript_sdk / "src/clientHeaders.ts").read_text()
    assert "## [Unreleased]\n\n## [0.7.0] - 2026-11-25\n" in (typescript_sdk / "CHANGELOG.md").read_text()


def test_in_actions_it_reports_the_versions_and_writes_the_notes(release, python_sdk, monkeypatch, tmp_path):
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    release.main(["minor", "--date", "2026-11-25", "--root", str(python_sdk), "--notes", str(tmp_path / "notes.md")])

    assert output.read_text() == "previous=0.6.2\nversion=0.7.0\n"
    assert (tmp_path / "notes.md").read_text() == "- New thing.\n"


@pytest.mark.parametrize(
    ("current", "wanted", "expected"),
    [
        ("0.6.2", "patch", "0.6.3"),
        ("0.6.2", "minor", "0.7.0"),
        ("0.6.2", "major", "1.0.0"),
        ("0.6.2", "0.10.0", "0.10.0"),
    ],
)
def test_next_version(release, current, wanted, expected):
    assert release.next_version(current, wanted) == expected


@pytest.mark.parametrize("wanted", ["0.6.2", "0.6.1", "0.7", "v0.7.0", "0.7.0\n", "0.07.0"])
def test_next_version_refuses_a_version_that_is_not_newer_or_malformed(release, wanted):
    with pytest.raises(SystemExit):
        release.next_version("0.6.2", wanted)


@pytest.mark.parametrize(
    ("changelog", "message"),
    [
        ("# Changelog\n\n## [Unreleased]\n\n## [0.6.2]\n\n- Old.\n", "is empty"),
        ("# Changelog\n\n## [0.6.2]\n\n- Old.\n", "has no"),
        ("# Changelog\n\n## [Unreleased]\n\n- New.\n\n## [0.7.0]\n\n- Old.\n", "already has a section"),
    ],
)
def test_changelog_problems_stop_the_release(release, changelog, message):
    with pytest.raises(SystemExit, match=message):
        release.release_changelog(changelog, "0.7.0", "2026-11-25")


def test_nothing_is_written_when_a_file_no_longer_holds_the_version(release, python_sdk):
    (python_sdk / "geonode_scraper_sdk/api_client.py").write_text("        self.user_agent = 'something-else'\n")

    with pytest.raises(SystemExit, match="api_client.py"):
        release.main(["minor", "--root", str(python_sdk)])

    assert 'version = "0.6.2"' in (python_sdk / "pyproject.toml").read_text()
    assert "## [Unreleased]\n\n- New thing." in (python_sdk / "CHANGELOG.md").read_text()


def test_input_after_double_dash_is_a_version_not_an_option(release, python_sdk):
    # Prepare release passes the form input as `-- "$WANTED"`, so `-h` must fail as a version, not print help.
    with pytest.raises(SystemExit, match="Version must look like"):
        release.main(["--root", str(python_sdk), "--", "-h"])

    assert 'version = "0.6.2"' in (python_sdk / "pyproject.toml").read_text()


def test_a_version_line_found_twice_stops_the_release(release, python_sdk):
    (python_sdk / "geonode_scraper_sdk/__init__.py").write_text('__version__ = "0.6.2"\n__version__ = "0.6.2"\n')

    with pytest.raises(SystemExit, match="got 2"):
        release.version_changes(python_sdk, "minor")


def test_package_json_edit_must_change_only_the_top_level_version(release, typescript_sdk):
    # The indented line the script edits belongs to a nested object here, not to the package.
    (typescript_sdk / "package.json").write_text(
        '{\n"name": "sdk",\n"version": "0.6.2",\n"engines": {\n  "version": "0.6.2",\n  "node": ">=20"\n}\n}\n'
    )

    with pytest.raises(SystemExit, match="more than the top-level version"):
        release.version_changes(typescript_sdk, "minor")


def test_package_lock_not_written_by_npm_stops_the_release(release, typescript_sdk):
    lock = json.loads((typescript_sdk / "package-lock.json").read_text())
    (typescript_sdk / "package-lock.json").write_text(json.dumps(lock, indent=4) + "\n")

    with pytest.raises(SystemExit, match="npm's own format"):
        release.version_changes(typescript_sdk, "minor")


def test_this_repository_records_its_version_where_the_script_expects(release):
    # Fails when regeneration or a hand edit moves a version line, before anyone tries to release.
    old, new, changes = release.version_changes(REPO, "patch")

    assert release.parse(new) > release.parse(old)
    assert all(text.count(new) for text in changes.values())
