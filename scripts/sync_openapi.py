#!/usr/bin/env python3
"""Bring openapi.json in line with the production API spec.

Fetches the spec (a URL or a local file), strips internal-only paths with
openapi-generator/filter_spec.py and compares the result with the committed
openapi.json. When they differ, it rewrites openapi.json, adds an entry under
``## [Unreleased]`` in CHANGELOG.md and can write a Markdown summary of the
differences for a pull request. Regenerating the SDK is left to
scripts/generate.sh.

The last line on stdout is ``changed=true`` or ``changed=false``, so a GitHub
Actions step can append it to ``$GITHUB_OUTPUT``. Everything else goes to stderr.

Usage:
    python3 scripts/sync_openapi.py [--source URL_OR_PATH] [--summary PATH] [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import urllib.request
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = REPO_ROOT / "openapi.json"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"
FILTER_SCRIPT = REPO_ROOT / "openapi-generator" / "filter_spec.py"
DEFAULT_SOURCE = "https://scraper.geonode.io/openapi.json"
UNRELEASED_HEADING = "## [Unreleased]"
METHODS = ("get", "put", "post", "delete", "patch")
# Top-level keys this repo sets itself: the API spec has no `servers`, and without it the client defaults to localhost.
REPO_OWNED_KEYS = ("servers",)


@dataclass
class SpecDiff:
    """What a reader of the SDK would notice between two filtered specs."""

    added_operations: list[str] = field(default_factory=list)
    removed_operations: list[str] = field(default_factory=list)
    added_parameters: list[str] = field(default_factory=list)
    removed_parameters: list[str] = field(default_factory=list)
    added_schemas: list[str] = field(default_factory=list)
    removed_schemas: list[str] = field(default_factory=list)
    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    added_enum_values: list[str] = field(default_factory=list)
    removed_enum_values: list[str] = field(default_factory=list)
    newly_required: list[str] = field(default_factory=list)
    no_longer_required: list[str] = field(default_factory=list)
    added_responses: list[str] = field(default_factory=list)
    removed_responses: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(getattr(self, f.name) for f in fields(self))


# (attribute, label in the pull request summary, label in the changelog or None to leave it out)
_ROWS = (
    ("added_operations", "New endpoints", "New endpoints"),
    ("removed_operations", "Removed endpoints", "Removed endpoints"),
    ("added_parameters", "New request parameters", "New request parameters"),
    ("removed_parameters", "Removed request parameters", "Removed request parameters"),
    ("added_schemas", "New models", "New models"),
    ("removed_schemas", "Removed models", "Removed models"),
    ("added_fields", "New model fields", "New model fields"),
    ("removed_fields", "Removed model fields", "Removed model fields"),
    ("added_enum_values", "New enum values", "New enum values"),
    ("removed_enum_values", "Removed enum values", "Removed enum values"),
    ("newly_required", "Fields that became required", "Fields that became required"),
    ("no_longer_required", "Fields that became optional", "Fields that became optional"),
    ("added_responses", "New documented response codes", None),
    ("removed_responses", "Removed documented response codes", None),
)


def load_filter() -> Callable[[dict], dict]:
    module_spec = importlib.util.spec_from_file_location("filter_spec", FILTER_SCRIPT)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Cannot load {FILTER_SCRIPT}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.filter_spec


def fetch(source: str) -> dict:
    if source.startswith(("https://", "http://")):
        request = urllib.request.Request(source, headers={"User-Agent": "geonode-sdk-openapi-sync"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def dump(spec: dict) -> str:
    """Serialise the way filter_spec.py does, so an unchanged spec compares equal byte for byte."""
    return json.dumps(spec, indent=4, sort_keys=True, ensure_ascii=False) + "\n"


def check_plausible(old: dict, new: dict) -> None:
    """Refuse a spec that looks broken rather than changed, so a bad deploy cannot wipe the SDK."""
    if "openapi" not in new or not isinstance(new.get("paths"), dict):
        raise SystemExit("The fetched document is not an OpenAPI spec")
    old_count, new_count = len(old.get("paths", {})), len(new["paths"])
    if new_count * 2 < old_count:
        raise SystemExit(f"The fetched spec has {new_count} paths, down from {old_count}; refusing to sync")


def _operations(spec: dict) -> dict[str, dict]:
    operations = {}
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if method in METHODS and isinstance(operation, dict):
                operations[f"{method.upper()} {path}"] = operation
    return operations


def _parameter_names(operation: dict) -> set[str]:
    return {p["name"] for p in operation.get("parameters", []) if isinstance(p, dict) and "name" in p}


def _enum_values(schema: dict) -> list[str]:
    """Allowed values of a schema, including the `anyOf: [{enum}, {type: null}]` form of optional fields."""
    values: list[str] = []
    for part in [schema, *schema.get("anyOf", []), *schema.get("oneOf", [])]:
        if isinstance(part, dict):
            values += [str(v) for v in part.get("enum") or []]
            if "const" in part:
                values.append(str(part["const"]))
    return values


def _diff_values(before: list[str], after: list[str], where: str) -> tuple[list[str], list[str]]:
    added = [f"`{v}` in `{where}`" for v in after if v not in before]
    removed = [f"`{v}` in `{where}`" for v in before if v not in after]
    return added, removed


def compare(old: dict, new: dict) -> SpecDiff:
    diff = SpecDiff()

    old_ops, new_ops = _operations(old), _operations(new)
    diff.added_operations = [f"`{op}`" for op in sorted(new_ops.keys() - old_ops.keys())]
    diff.removed_operations = [f"`{op}`" for op in sorted(old_ops.keys() - new_ops.keys())]
    for op in sorted(old_ops.keys() & new_ops.keys()):
        before, after = _parameter_names(old_ops[op]), _parameter_names(new_ops[op])
        diff.added_parameters += [f"`{name}` on `{op}`" for name in sorted(after - before)]
        diff.removed_parameters += [f"`{name}` on `{op}`" for name in sorted(before - after)]
        codes_before = set(old_ops[op].get("responses", {}))
        codes_after = set(new_ops[op].get("responses", {}))
        diff.added_responses += [f"`{code}` on `{op}`" for code in sorted(codes_after - codes_before)]
        diff.removed_responses += [f"`{code}` on `{op}`" for code in sorted(codes_before - codes_after)]

    old_schemas = old.get("components", {}).get("schemas", {})
    new_schemas = new.get("components", {}).get("schemas", {})
    diff.added_schemas = [f"`{name}`" for name in sorted(new_schemas.keys() - old_schemas.keys())]
    diff.removed_schemas = [f"`{name}`" for name in sorted(old_schemas.keys() - new_schemas.keys())]
    for name in sorted(old_schemas.keys() & new_schemas.keys()):
        before, after = old_schemas[name], new_schemas[name]
        props_before, props_after = before.get("properties") or {}, after.get("properties") or {}
        diff.added_fields += [f"`{name}.{prop}`" for prop in sorted(props_after.keys() - props_before.keys())]
        diff.removed_fields += [f"`{name}.{prop}`" for prop in sorted(props_before.keys() - props_after.keys())]
        added, removed = _diff_values(_enum_values(before), _enum_values(after), name)
        for prop in sorted(props_before.keys() & props_after.keys()):
            before_values, after_values = _enum_values(props_before[prop]), _enum_values(props_after[prop])
            more, fewer = _diff_values(before_values, after_values, f"{name}.{prop}")
            added, removed = added + more, removed + fewer
        diff.added_enum_values += added
        diff.removed_enum_values += removed
        required_before, required_after = set(before.get("required") or []), set(after.get("required") or [])
        diff.newly_required += [f"`{name}.{prop}`" for prop in sorted(required_after - required_before)]
        diff.no_longer_required += [f"`{name}.{prop}`" for prop in sorted(required_before - required_after)]

    return diff


def changelog_entry(diff: SpecDiff) -> list[str]:
    # No date here: the same spec must give the same commit every night, so an open sync PR is left alone.
    lines = ["- Synced with the production API spec."]
    listed = False
    for attr, _, label in _ROWS:
        items = getattr(diff, attr)
        if label and items:
            lines.append(f"  - {label}: {', '.join(items)}.")
            listed = True
    if not listed:
        lines.append("  - Descriptions, types or constraints changed; see the API reference.")
    return lines


def add_changelog_entry(changelog: str, entry: list[str]) -> str:
    """Put the entry first under ``## [Unreleased]``, keeping any notes already there."""
    lines = changelog.splitlines()
    if UNRELEASED_HEADING not in lines:
        raise SystemExit(f"CHANGELOG.md has no '{UNRELEASED_HEADING}' heading")
    start = lines.index(UNRELEASED_HEADING) + 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    rest = lines[start:]
    gap = [""] if rest and not rest[0].startswith("- ") else []
    return "\n".join(lines[: lines.index(UNRELEASED_HEADING) + 1] + ["", *entry, *gap, *rest]) + "\n"


def summary_markdown(diff: SpecDiff, source: str, date: str) -> str:
    out = [
        "## What changed in the API spec",
        "",
        f"Source: `{source}`, fetched on {date} (UTC) and filtered with `openapi-generator/filter_spec.py`.",
        "",
    ]
    if diff.is_empty():
        out.append("Only descriptions, types or constraints changed: no endpoint, parameter, model or enum value.")
    else:
        out += ["| Change | Items |", "| --- | --- |"]
        out += [f"| {label} | {', '.join(getattr(diff, attr))} |" for attr, label, _ in _ROWS if getattr(diff, attr)]
    out += [
        "",
        "## Before merging",
        "",
        "- CI runs on this pull request. If a breaking change fails the tests, fix them in this branch: "
        "the nightly sync does not overwrite commits pushed by people.",
        "- Removed parameters or fields break code that calls this SDK, including our packages built on it "
        "(for the Python SDK, `geonode-scraper-tools-core`). Release fixed versions of those first.",
        "- Merging publishes nothing. A release is a separate version pull request and the manual Publish workflow.",
        "",
    ]
    return "\n".join(out)


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="URL or file of the full API spec")
    parser.add_argument("--summary", type=Path, help="write a Markdown summary of the differences here")
    parser.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    args = parser.parse_args(argv)

    old_text = SPEC_FILE.read_text(encoding="utf-8")
    new_spec = load_filter()(fetch(args.source))
    old_spec = json.loads(old_text)
    check_plausible(old_spec, new_spec)
    for key in REPO_OWNED_KEYS:
        if key in old_spec:
            new_spec[key] = old_spec[key]
    new_text = dump(new_spec)

    if new_text == old_text:
        print("openapi.json already matches the source spec", file=sys.stderr)
        print("changed=false")
        return 0

    diff = compare(old_spec, new_spec)
    new_changelog = add_changelog_entry(CHANGELOG_FILE.read_text(encoding="utf-8"), changelog_entry(diff))
    _write(SPEC_FILE, new_text)
    _write(CHANGELOG_FILE, new_changelog)
    if args.summary:
        _write(args.summary, summary_markdown(diff, args.source, args.date))
    print("openapi.json updated; run scripts/generate.sh next", file=sys.stderr)
    print("changed=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
