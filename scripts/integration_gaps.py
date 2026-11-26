#!/usr/bin/env python3
"""List what the hand-written integrations (n8n, Make, Zapier) lack, or still use, after an API spec change.

Reads clones of geonodecom/integration-n8n, integration-make and integration-zapier from one directory and compares
the endpoints they call with the public endpoints of the spec. Make is read from its module definitions; n8n and
Zapier from their source code, so the result points a reviewer at likely gaps rather than proving them. The nightly
sync adds the Markdown to its pull request; without --before the script prints today's coverage for a hand run.
The same script is kept in geonodecom/sdk-python and geonodecom/sdk-typescript.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

REPOS = {"n8n": "integration-n8n", "Make": "integration-make", "Zapier": "integration-zapier"}
METHODS = ("get", "post", "put", "patch", "delete")
# A request object in n8n or Zapier code, `method: 'GET', url: '/v1/...'` or `path: '/v1/...', method: 'POST'`.
REQUESTS = (
    re.compile(
        r"method:\s*['\"](?P<method>[A-Za-z]+)['\"]\s*,\s*\b(?:url|path):\s*(?P<q>[`'\"])(?P<url>[^`'\"]*)(?P=q)"
    ),
    re.compile(
        r"\b(?:url|path):\s*(?P<q>[`'\"])(?P<url>[^`'\"]*)(?P=q)\s*,\s*method:\s*['\"](?P<method>[A-Za-z]+)['\"]"
    ),
)
# Any string or template literal holding an API path, such as a polling URL built as `/v1/crawl/${jobId}`.
LITERAL = re.compile(r"[`'\"][^`'\"\n]*?(/v1/[^`'\"\s]*)[`'\"]")
VARIABLE_RESOURCE = re.compile(r"^/v1/\$\{[^}]+\}")


def norm(path: str) -> str:
    """Path with its query dropped and every placeholder ({id}, ${id}, {{id}}) written as {}."""
    path = re.sub(r"\$\{[^}]*\}|\{\{[^}]*\}\}|\{[^}]*\}", "{}", path.split("?")[0])
    return path.rstrip("/") or "/"


@dataclass
class Usage:
    calls: set[tuple[str | None, str]] = field(default_factory=set)  # (method or None when unknown, normalized path)
    query: dict[str, set[str]] = field(default_factory=dict)  # Make only: "METHOD path" -> query keys it sends
    files: list[tuple[str, str, set[tuple[str | None, str]]]] = field(default_factory=list)  # name, text, calls
    text: str = ""
    commit: str = ""
    error: str = ""

    def calls_op(self, method: str, path: str) -> bool:
        return (method, norm(path)) in self.calls

    def may_send(self, method: str, path: str, name: str) -> bool:
        """A field with this name declared in a file that calls the endpoint, or in a declarations-only file named
        after its resource (n8n's `ExtractDescription.ts`)."""
        resource = path.split("/")[2] if path.startswith("/v1/") else ""
        return any(
            ((method, norm(path)) in calls or (not calls and resource and resource in file_name.lower()))
            and declares_field(text, name)
            for file_name, text, calls in self.files
        )


def read_make(root: Path) -> Usage:
    usage = Usage()
    prefix = urlparse(json.loads((root / "base.imljson").read_text(encoding="utf-8-sig"))["baseUrl"]).path.rstrip("/")
    for file in sorted(root.rglob("api.imljson")):
        data = json.loads(file.read_text(encoding="utf-8-sig"))
        for call in data if isinstance(data, list) else [data]:
            url = str(call.get("url", ""))
            if "{{parameters.url}}" in url:  # the generic "make an API call" module reaches any endpoint
                continue
            path = norm(urlparse(url).path if url.startswith("http") else prefix + url)
            method = str(call.get("method", "GET")).upper()
            usage.calls.add((method, path))
            keys = set()
            for qs in (call.get("qs"), (call.get("pagination") or {}).get("qs")):
                if isinstance(qs, dict):
                    keys |= set(qs)
            usage.query.setdefault(f"{method} {path}", set()).update(keys)
    usage.text = "\n".join(f.read_text(encoding="utf-8-sig", errors="replace") for f in sorted(root.rglob("*.imljson")))
    return usage


def add_calls(calls: set[tuple[str | None, str]], method: str, url: str, named: set[str]) -> None:
    path = url[url.find("/v1/") :]
    if VARIABLE_RESOURCE.match(path):
        targets = [VARIABLE_RESOURCE.sub(f"/v1/{r}", path, count=1) for r in named]
    else:
        targets = [path]
    for target in targets:
        calls.add((method.upper(), norm(target)))


def read_code(root: Path, patterns: list[str], resources: set[str]) -> Usage:
    usage = Usage()
    texts = []
    for pattern in patterns:
        for file in sorted(root.glob(pattern)):
            if "sample" in file.name or "node_modules" in file.parts:
                continue
            text = file.read_text(errors="replace")
            texts.append(text)
            # For `/v1/${jobType}/...`, the resources this file names as strings (Zapier's job types).
            named = {r for r in resources if re.search(rf"['\"]{re.escape(r)}['\"]", text)}
            calls: set[tuple[str | None, str]] = set()
            in_requests = []
            for request in REQUESTS:
                for match in request.finditer(text):
                    if "/v1/" in match["url"]:
                        add_calls(calls, match["method"], match["url"], named)
                        in_requests.append(match.span("url"))
            # Any other path written without a method is a status or polling URL, so a GET.
            for match in LITERAL.finditer(text):
                if not any(start <= match.start(1) < end for start, end in in_requests):
                    add_calls(calls, "GET", match.group(1), named)
            usage.calls |= calls
            usage.files.append((file.name, text, calls))
    usage.text = "\n".join(texts)
    return usage


def read_integrations(sources: Path, resources: set[str]) -> dict[str, Usage]:
    readers = {
        "n8n": lambda root: read_code(root, ["nodes/**/*.ts", "credentials/*.ts"], resources),
        "Make": read_make,
        "Zapier": lambda root: read_code(
            root, ["creates/*.js", "searches/*.js", "triggers/*.js", "lib/*.js", "*.js"], resources
        ),
    }
    result = {}
    for name, repo in REPOS.items():
        root = sources / repo
        try:
            usage = readers[name](root) if root.is_dir() else Usage(error="not cloned")
        except Exception as exc:  # noqa: BLE001 - one unreadable integration must not hide the others
            usage = Usage(error=f"{type(exc).__name__}: {exc}")
        if not usage.error and not usage.calls:
            usage.error = "no API calls found; its layout may have changed"
        if root.is_dir():
            git = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
            )
            usage.commit = git.stdout.strip()
        result[name] = usage
    return result


def public(path: str) -> bool:
    return path != "/health" and not path.startswith("/v1/internal/")


def operations(spec: dict) -> dict[tuple[str, str], dict]:
    return {
        (method.upper(), path): op
        for path, item in spec.get("paths", {}).items()
        if public(path)
        for method, op in item.items()
        if method in METHODS
    }


def deref(spec: dict, node: dict) -> tuple[str | None, dict]:
    """The schema a $ref points at, with its components name, or the node itself."""
    if isinstance(node, dict) and str(node.get("$ref", "")).startswith("#/components/"):
        parts = node["$ref"][2:].split("/")
        target = spec
        for part in parts:
            target = target.get(part, {})
        return parts[-1], target
    return None, node


def query_params(spec: dict, path: str, method: str) -> set[str]:
    item = spec["paths"][path]
    params = list(item.get("parameters", [])) + list(item[method.lower()].get("parameters", []))
    return {p["name"] for p in (deref(spec, p)[1] for p in params) if p.get("in") == "query"}


def request_enums(spec: dict) -> dict[str, set[str]]:
    """Enum values a client can send, keyed like `SearchRequest.engine` or `GET /v1/x ?param`."""
    found: dict[str, set[str]] = {}
    seen: set[str] = set()

    def enums_of(node: dict) -> set[str]:
        values = set(map(str, node.get("enum", [])))
        for child in [node.get("items", {}), *node.get("anyOf", []), *node.get("oneOf", [])]:
            if isinstance(child, dict) and child and "$ref" not in child:
                values |= enums_of(child)
        return values

    def visit(label: str, node: dict) -> None:
        name, schema = deref(spec, node)
        if name:
            if name in seen:
                return
            seen.add(name)
            label = name
        if values := enums_of(schema):
            found.setdefault(label, set()).update(values)
        for prop, child in schema.get("properties", {}).items():
            visit(f"{label}.{prop}", child)
        for child in [
            schema.get("items", {}),
            *schema.get("anyOf", []),
            *schema.get("oneOf", []),
            *schema.get("allOf", []),
        ]:
            if isinstance(child, dict) and child:
                visit(label, child)

    for (method, path), op in operations(spec).items():
        for media in (op.get("requestBody", {}).get("content") or {}).values():
            visit(f"{method} {path}", media.get("schema", {}))
        params = list(spec["paths"][path].get("parameters", [])) + list(op.get("parameters", []))
        for param in (deref(spec, p)[1] for p in params):
            if param.get("in") == "query":
                visit(f"{method} {path} ?{param['name']}", param.get("schema", {}))
    return found


def mentions(text: str, value: str) -> bool:
    return re.search(rf"[`'\"]{re.escape(value)}[`'\"]", text) is not None


def declares_field(text: str, name: str) -> bool:
    """An input field with this name, as n8n (`name: 'x'`) and Zapier (`key: 'x'`) declare them."""
    return re.search(rf"\b(?:name|key):\s*['\"]{re.escape(name)}['\"]", text) is not None


def report(after: dict, usages: dict[str, Usage], before: dict | None = None) -> str:
    names = list(REPOS)
    after_ops = operations(after)
    out = ["## Integrations: n8n, Make, Zapier", ""]
    read = [f"geonodecom/{REPOS[n]} `{usages[n].commit or 'unknown'}`" for n in names]
    out += [
        f"Read from the default branches: {', '.join(read)}. Make is read from its module definitions, n8n and "
        "Zapier from their source code, so this points at likely gaps rather than proving them. Response fields, "
        "headers and webhook payloads are not checked. The bot does not change the integrations.",
        "",
    ]
    readable = [n for n in names if not usages[n].error]

    if before is not None:
        # Keyed by the normalized path, so renaming `{job_id}` to `{crawl_id}` is not a removal.
        old = {(m, norm(p)): p for m, p in operations(before)}
        new = {(m, norm(p)): p for m, p in after_ops}
        lines = []
        for key in sorted(set(old) - set(new), key=lambda k: (k[1], k[0])):
            method, path = key[0], old[key]
            who = [n for n in readable if usages[n].calls_op(method, path)]
            if who:
                verb = "calls" if len(who) == 1 else "call"
                lines.append(f"- `{method} {path}` is gone: {', '.join(who)} still {verb} it.")
        for key in sorted(set(old) & set(new), key=lambda k: (k[1], k[0])):
            method, path = key[0], new[key]
            for param in sorted(query_params(before, old[key], method) - query_params(after, path, method)):
                sends, maybe = [], []
                for n in readable:
                    if not usages[n].calls_op(method, path):
                        continue
                    if n == "Make":
                        if param in usages[n].query.get(f"{method} {norm(path)}", set()):
                            sends.append(n)
                    elif usages[n].may_send(method, path, param):
                        maybe.append(n)
                parts = ([f"{', '.join(sends)} still sends it"] if sends else []) + (
                    [f"{', '.join(maybe)} may still send it (a `{param}` field next to that call)"] if maybe else []
                )
                if parts:
                    lines.append(f"- `{method} {path}` no longer takes `{param}`: {'; '.join(parts)}.")
        old_enums, new_enums = request_enums(before), request_enums(after)
        # Only fields that still exist: a whole removed endpoint is reported above.
        for label in sorted(set(old_enums) & set(new_enums)):
            for value in sorted(old_enums[label] - new_enums[label]):
                who = [n for n in readable if mentions(usages[n].text, value)]
                if who:
                    verb = "offers" if len(who) == 1 else "offer"
                    lines.append(f"- `{value}` is no longer allowed in `{label}`: {', '.join(who)} still {verb} it.")
        out += ["**Removed by this sync and still used**", ""] + (lines or ["Nothing."]) + [""]

        rows = []
        for key in sorted(set(new) - set(old), key=lambda k: (k[1], k[0])):
            method, path = key[0], new[key]
            rows.append([f"`{method} {path}`"] + [mark(usages[n], usages[n].calls_op(method, path)) for n in names])
        # New values of fields that existed before; a new endpoint's own fields come with its row above.
        for label in sorted(set(new_enums) & set(old_enums)):
            for value in sorted(new_enums[label] - old_enums[label]):
                rows.append(
                    [f"`{value}` in `{label}`"] + [mark(usages[n], mentions(usages[n].text, value)) for n in names]
                )
        out += ["**New in this sync**", ""]
        out += table(["New", *names], rows) if rows else ["Nothing new for them to pick up."]
        out += [""]

    unreadable = [f"{n} ({usages[n].error})" for n in names if usages[n].error]
    if unreadable:
        out += [f"**Could not read:** {'; '.join(unreadable)}.", ""]

    ops = sorted(after_ops, key=lambda op: (op[1], op[0]))
    counts = ", ".join(f"{n} {sum(usages[n].calls_op(m, p) for m, p in ops)} of {len(ops)}" for n in readable)
    full = table(
        ["Endpoint", *names],
        [[f"`{m} {p}`"] + [mark(usages[n], usages[n].calls_op(m, p)) for n in names] for m, p in ops],
    )
    if before is not None:
        out += [f"<details><summary>Every endpoint ({counts})</summary>", "", *full, "", "</details>", ""]
    else:
        out += [f"**Every endpoint** ({counts})", "", *full, ""]
    return "\n".join(out)


def mark(usage: Usage, used: bool) -> str:
    if usage.error:
        return "?"
    return "✓" if used else "—"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)] + [
        "| " + " | ".join(r) + " |" for r in rows
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--after", type=Path, required=True, help="the spec after the sync (openapi.json)")
    parser.add_argument("--before", type=Path, help="the spec before the sync; without it, only today's coverage")
    parser.add_argument("--sources", type=Path, required=True, help="directory with the three integration clones")
    parser.add_argument("--out", type=Path, help="write the Markdown here instead of printing it")
    args = parser.parse_args(argv)

    after = json.loads(args.after.read_text(encoding="utf-8"))
    before = json.loads(args.before.read_text(encoding="utf-8")) if args.before else None
    specs = [after] + ([before] if before else [])
    resources = {path.split("/")[2] for spec in specs for _, path in operations(spec) if path.startswith("/v1/")}
    usages = read_integrations(args.sources, resources)
    for name, usage in usages.items():
        if usage.error:
            # On stdout when the report goes to a file, where Actions reads workflow commands.
            print(f"::warning::Could not read {name}: {usage.error}", file=sys.stdout if args.out else sys.stderr)
    text = report(after, usages, before)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
