#!/usr/bin/env python3
"""Strip internal-only endpoints from an OpenAPI spec, with the schemas and
security schemes only they use.

Run it on the backend's spec to produce ``openapi.json``; the generate scripts
run it again before openapi-generator, so the internal surface never lands in
the repo or the published SDKs.

Usage:
    python3 filter_spec.py <input_spec.json> <output_spec.json>
"""

from __future__ import annotations

import json
import sys

# Every path under this prefix is internal-only.
INTERNAL_PREFIX = "/v1/internal/"


def _is_internal(path: str) -> bool:
    return path.startswith(INTERNAL_PREFIX)


def _collect_refs(node: object, acc: set[str]) -> None:
    """Walk an arbitrary JSON node and collect every component schema name it $refs."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                acc.add(value.rsplit("/", 1)[-1])
            else:
                _collect_refs(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, acc)


def _reachable_schemas(seed: set[str], schemas: dict[str, object]) -> set[str]:
    """Transitive closure of schema names reachable from ``seed``."""
    seen: set[str] = set()
    stack = list(seed)
    while stack:
        name = stack.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        refs: set[str] = set()
        _collect_refs(schemas[name], refs)
        stack.extend(refs)
    return seen


def _path_schema_seed(paths: dict[str, object], keep: bool) -> set[str]:
    """$refs reached directly from the kept (or excluded) subset of paths."""
    seed: set[str] = set()
    for path, node in paths.items():
        if _is_internal(path) == keep:  # keep=True wants public paths; keep=False wants internal
            continue
        _collect_refs(node, seed)
    return seed


def _used_security_schemes(spec: dict) -> set[str]:
    """Security scheme names required globally or by any remaining operation."""
    used: set[str] = set()
    requirements = list(spec.get("security", []))
    for node in spec.get("paths", {}).values():
        for operation in node.values():
            if isinstance(operation, dict):
                requirements.extend(operation.get("security", []))
    for requirement in requirements:
        used.update(requirement)
    return used


def filter_spec(spec: dict) -> dict:
    paths = spec.get("paths", {})
    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    internal_present = [p for p in paths if _is_internal(p)]
    if internal_present:
        kept_schemas = _reachable_schemas(_path_schema_seed(paths, keep=True), schemas)
        internal_schemas = _reachable_schemas(_path_schema_seed(paths, keep=False), schemas)

        for path in internal_present:
            del paths[path]
        # Only drop schemas reachable solely from internal paths.
        for name in internal_schemas - kept_schemas:
            schemas.pop(name, None)

    security_schemes = components.get("securitySchemes", {})
    for name in set(security_schemes) - _used_security_schemes(spec):
        del security_schemes[name]

    return spec


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <input_spec.json> <output_spec.json>", file=sys.stderr)
        return 2

    with open(argv[1], encoding="utf-8") as fh:
        spec = json.load(fh)

    filtered = filter_spec(spec)

    with open(argv[2], "w", encoding="utf-8", newline="\n") as fh:
        json.dump(filtered, fh, indent=4, sort_keys=True, ensure_ascii=False)
        fh.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
