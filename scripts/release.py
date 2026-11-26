#!/usr/bin/env python3
"""Prepare a release: set the version everywhere the SDK records it and turn ``[Unreleased]`` into a version section.

Usage: ``python3 scripts/release.py 0.7.0`` (or ``patch``, ``minor``, ``major``). The same script is kept in
geonodecom/sdk-python and geonodecom/sdk-typescript; it finds out which SDK it is in from the files present.
It only edits files. The Prepare release workflow runs it on main and opens the "Release X.Y.Z" pull request;
after merging, run the Publish workflow.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
UNRELEASED_HEADING = "## [Unreleased]"
# Semver without leading zeros; matched in full, so a trailing newline from a form or the API is refused.
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


@dataclass(frozen=True)
class Replace:
    """One line holding the version, found with ``pattern`` (``{v}`` stands for the version)."""

    path: str
    pattern: str

    def apply(self, text: str, old: str, new: str) -> str:
        regex = re.compile(self.pattern.replace("{v}", re.escape(old)), re.MULTILINE)
        matches = regex.findall(text)
        if len(matches) != 1:
            raise SystemExit(f"{self.path}: expected one line matching {self.pattern!r} for {old}, got {len(matches)}")
        return regex.sub(lambda m: m.group(0).replace(old, new), text)


@dataclass(frozen=True)
class Sdk:
    name: str
    marker: str
    current: Callable[[Path], str]
    edits: tuple[Replace, ...]
    package_lock: bool


def python_version(root: Path) -> str:
    match = re.search(r'^version = "([^"]+)"$', (root / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit('pyproject.toml has no `version = "..."` line')
    return match.group(1)


def package_version(root: Path) -> str:
    return json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]


SDKS = (
    Sdk(
        name="Python",
        marker="geonode_scraper_sdk/__init__.py",
        current=python_version,
        edits=(
            Replace("pyproject.toml", r'^version = "{v}"$'),
            Replace("geonode_scraper_sdk/__init__.py", r'^__version__ = "{v}"$'),
            # Generated from pyproject.toml by scripts/generate.sh; set here too so a release needs no regeneration.
            Replace("geonode_scraper_sdk/api_client.py", r"'geonode-python-sdk/{v}'"),
            Replace("geonode_scraper_sdk/configuration.py", r'"SDK Package Version: {v}"'),
        ),
        package_lock=False,
    ),
    Sdk(
        name="TypeScript",
        marker="src/clientHeaders.ts",
        current=package_version,
        edits=(
            Replace("package.json", r'^  "version": "{v}",$'),
            Replace("src/clientHeaders.ts", r'^export const SDK_VERSION = "{v}";$'),
        ),
        package_lock=True,
    ),
)


def detect(root: Path) -> Sdk:
    found = [sdk for sdk in SDKS if (root / sdk.marker).is_file()]
    if len(found) != 1:
        raise SystemExit(f"Cannot tell which SDK {root} holds")
    return found[0]


def parse(version: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(version)
    if not match:
        raise SystemExit(f"Version must look like 1.2.3, got {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def next_version(current: str, wanted: str) -> str:
    major, minor, patch = parse(current)
    bumped = {
        "major": f"{major + 1}.0.0",
        "minor": f"{major}.{minor + 1}.0",
        "patch": f"{major}.{minor}.{patch + 1}",
    }
    new = bumped.get(wanted, wanted)
    if parse(new) <= (major, minor, patch):
        raise SystemExit(f"New version {new} must be greater than the current {current}")
    return new


def release_changelog(text: str, version: str, date: str) -> str:
    """Move the ``[Unreleased]`` notes under a new version heading and leave an empty ``[Unreleased]`` above it."""
    lines = text.splitlines()
    if UNRELEASED_HEADING not in lines:
        raise SystemExit(f"CHANGELOG.md has no '{UNRELEASED_HEADING}' heading")
    if re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
        raise SystemExit(f"CHANGELOG.md already has a section for {version}")
    start = lines.index(UNRELEASED_HEADING) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## [")), len(lines))
    if not any(line.strip() for line in lines[start:end]):
        raise SystemExit(f"Nothing to release: '{UNRELEASED_HEADING}' in CHANGELOG.md is empty")
    heading = lines.index(UNRELEASED_HEADING)
    return "\n".join([*lines[: heading + 1], "", f"## [{version}] - {date}", *lines[start:]]) + "\n"


def notes(changelog: str, version: str) -> str:
    """The release notes under ``## [version]``, without the heading."""
    lines = changelog.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## [{version}]")) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## [")), len(lines))
    return "\n".join(lines[start:end]).strip() + "\n"


def release_package_lock(text: str, old: str, new: str) -> str:
    lock = json.loads(text)
    if json.dumps(lock, indent=2, ensure_ascii=False) + "\n" != text:
        raise SystemExit("package-lock.json is not in npm's own format; run `npm install` first")
    if lock.get("version") != old or lock["packages"][""].get("version") != old:
        raise SystemExit(f"package-lock.json does not record version {old}; run `npm install` first")
    lock["version"] = new
    lock["packages"][""]["version"] = new
    return json.dumps(lock, indent=2, ensure_ascii=False) + "\n"


def version_changes(root: Path, wanted: str) -> tuple[str, str, dict[str, str]]:
    """Return the current version, the new one and the new text of every file recording the version."""
    sdk = detect(root)
    old = sdk.current(root)
    new = next_version(old, wanted)
    changes: dict[str, str] = {}
    for edit in sdk.edits:
        changes[edit.path] = edit.apply((root / edit.path).read_text(encoding="utf-8"), old, new)
    if sdk.package_lock:
        changes["package-lock.json"] = release_package_lock(
            (root / "package-lock.json").read_text(encoding="utf-8"), old, new
        )
    if "package.json" in changes:
        before = json.loads((root / "package.json").read_text(encoding="utf-8"))
        after = json.loads(changes["package.json"])
        if after != {**before, "version": new}:
            raise SystemExit("package.json: the edit changed more than the top-level version")
    return old, new, changes


def plan(root: Path, wanted: str, date: str) -> tuple[str, str, dict[str, str]]:
    """Return the current version, the new one and the new text of every file to change, without writing."""
    old, new, changes = version_changes(root, wanted)
    changes["CHANGELOG.md"] = release_changelog((root / "CHANGELOG.md").read_text(encoding="utf-8"), new, date)
    return old, new, changes


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the new version, such as 0.7.0, or patch, minor or major")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="release date (default: today)")
    parser.add_argument("--notes", type=Path, help="also write the release notes to this file")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    old, new, changes = plan(args.root, args.version, args.date)
    for path, text in changes.items():
        (args.root / path).write_text(text, encoding="utf-8")
    if args.notes:
        args.notes.write_text(notes(changes["CHANGELOG.md"], new), encoding="utf-8")
    print(f"{detect(args.root).name} SDK {old} -> {new}. Updated:")
    for path in changes:
        print(f"- {path}")
    print(f'Commit as "Release {new}", open a pull request, merge it, then run the Publish workflow on main.')
    # The Prepare release workflow names its branch and pull request after the new version.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"previous={old}\nversion={new}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
