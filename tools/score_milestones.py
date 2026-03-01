#!/usr/bin/env python3
"""Score milestone checklists from repository evidence."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    ok: bool
    kind: str
    message: str
    details: dict[str, Any]
    children: list["CheckResult"]

    def flatten_failed(self) -> list["CheckResult"]:
        if not self.children:
            return [] if self.ok else [self]
        out: list[CheckResult] = []
        for child in self.children:
            out.extend(child.flatten_failed())
        if not out and not self.ok:
            out.append(self)
        return out

    def flatten_passed(self) -> list["CheckResult"]:
        if not self.children:
            return [self] if self.ok else []
        out: list[CheckResult] = []
        for child in self.children:
            out.extend(child.flatten_passed())
        if not out and self.ok:
            out.append(self)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "kind": self.kind,
            "message": self.message,
            "details": self.details,
            "children": [child.to_dict() for child in self.children],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve(repo_root: Path, raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (repo_root / p)


def _load_json(path: Path, cache: dict[Path, Any]) -> Any:
    path = path.resolve()
    if path not in cache:
        cache[path] = json.loads(path.read_text(encoding="utf-8"))
    return cache[path]


def _extract_json_path(payload: Any, json_path: str) -> tuple[bool, Any]:
    if json_path.strip() == "":
        return True, payload

    cur = payload
    for token in json_path.split("."):
        if token == "":
            return False, None
        if "[" in token:
            head = token
            indexes: list[int] = []
            while "[" in head:
                prefix, rest = head.split("[", 1)
                idx_txt, tail = rest.split("]", 1)
                if idx_txt == "" or not idx_txt.isdigit():
                    return False, None
                if prefix:
                    if not isinstance(cur, dict) or prefix not in cur:
                        return False, None
                    cur = cur[prefix]
                indexes.append(int(idx_txt))
                head = tail
            if head:
                if not isinstance(cur, dict) or head not in cur:
                    return False, None
                cur = cur[head]
            for idx in indexes:
                if not isinstance(cur, list) or idx < 0 or idx >= len(cur):
                    return False, None
                cur = cur[idx]
            continue

        if not isinstance(cur, dict) or token not in cur:
            return False, None
        cur = cur[token]

    return True, cur


def _glob_paths(repo_root: Path, pattern: str) -> list[Path]:
    base = repo_root
    return sorted(path for path in base.glob(pattern) if path.exists())


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _result(ok: bool, kind: str, message: str, details: dict[str, Any] | None = None, children: list[CheckResult] | None = None) -> CheckResult:
    return CheckResult(ok=ok, kind=kind, message=message, details=details or {}, children=children or [])


def _eval_leaf(check: dict[str, Any], *, repo_root: Path, json_cache: dict[Path, Any]) -> CheckResult:
    ctype = str(check.get("type", "")).strip()
    if ctype == "":
        return _result(False, "invalid", "missing check type")

    if ctype == "file_exists":
        raw = str(check.get("path", ""))
        path = _resolve(repo_root, raw)
        ok = path.is_file()
        return _result(ok, ctype, f"file exists: {raw}", {"path": _rel(path, repo_root), "exists": ok})

    if ctype == "directory_exists":
        raw = str(check.get("path", ""))
        path = _resolve(repo_root, raw)
        ok = path.is_dir()
        return _result(ok, ctype, f"directory exists: {raw}", {"path": _rel(path, repo_root), "exists": ok})

    if ctype == "glob_count_at_least":
        pattern = str(check.get("glob", ""))
        min_count = int(check.get("min", 1))
        matches = _glob_paths(repo_root, pattern)
        ok = len(matches) >= min_count
        return _result(
            ok,
            ctype,
            f"glob count >= {min_count}: {pattern}",
            {
                "glob": pattern,
                "min": min_count,
                "count": len(matches),
                "matches": [_rel(p, repo_root) for p in matches[:20]],
            },
        )

    if ctype == "regex_in_file":
        raw = str(check.get("path", ""))
        pattern = str(check.get("pattern", ""))
        flags = 0
        if bool(check.get("ignoreCase")):
            flags |= re.IGNORECASE
        path = _resolve(repo_root, raw)
        if not path.is_file():
            return _result(False, ctype, f"regex in file: {raw}", {"path": _rel(path, repo_root), "error": "file missing"})
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        ok = re.search(pattern, text, flags) is not None
        return _result(ok, ctype, f"regex in file: {raw}", {"path": _rel(path, repo_root), "pattern": pattern})

    if ctype == "text_file_value_equals":
        raw = str(check.get("path", ""))
        expected = str(check.get("equals", ""))
        path = _resolve(repo_root, raw)
        if not path.is_file():
            return _result(False, ctype, f"text value equals in {raw}", {"path": _rel(path, repo_root), "error": "file missing"})
        value = path.read_text(encoding="utf-8").strip()
        ok = value == expected
        return _result(ok, ctype, f"text value equals in {raw}", {"expected": expected, "actual": value, "path": _rel(path, repo_root)})

    if ctype == "json_path_equals":
        raw = str(check.get("path", ""))
        json_path = str(check.get("jsonPath", ""))
        expected = check.get("equals")
        path = _resolve(repo_root, raw)
        if not path.is_file():
            return _result(False, ctype, f"json path equals in {raw}", {"path": _rel(path, repo_root), "error": "file missing"})
        try:
            payload = _load_json(path, json_cache)
        except Exception as exc:  # pragma: no cover - defensive path
            return _result(False, ctype, f"json path equals in {raw}", {"path": _rel(path, repo_root), "error": str(exc)})
        found, value = _extract_json_path(payload, json_path)
        ok = found and value == expected
        return _result(
            ok,
            ctype,
            f"json path equals in {raw}",
            {"path": _rel(path, repo_root), "jsonPath": json_path, "expected": expected, "found": found, "actual": value},
        )

    if ctype == "json_any_match":
        pattern = str(check.get("glob", ""))
        json_path = str(check.get("jsonPath", ""))
        expected = check.get("equals")
        min_matches = int(check.get("minMatches", 1))
        matches = _glob_paths(repo_root, pattern)
        hit_paths: list[str] = []
        for p in matches:
            if not p.is_file():
                continue
            try:
                payload = _load_json(p, json_cache)
            except Exception:
                continue
            found, value = _extract_json_path(payload, json_path)
            if found and value == expected:
                hit_paths.append(_rel(p, repo_root))
        ok = len(hit_paths) >= min_matches
        return _result(
            ok,
            ctype,
            f"json any match {json_path} == {expected!r}",
            {
                "glob": pattern,
                "jsonPath": json_path,
                "expected": expected,
                "minMatches": min_matches,
                "matches": len(hit_paths),
                "matchPaths": hit_paths[:20],
            },
        )

    if ctype == "json_any_match_non_null":
        pattern = str(check.get("glob", ""))
        json_path = str(check.get("jsonPath", ""))
        min_matches = int(check.get("minMatches", 1))
        matches = _glob_paths(repo_root, pattern)
        hit_paths: list[str] = []
        for p in matches:
            if not p.is_file():
                continue
            try:
                payload = _load_json(p, json_cache)
            except Exception:
                continue
            found, value = _extract_json_path(payload, json_path)
            if found and value is not None:
                hit_paths.append(_rel(p, repo_root))
        ok = len(hit_paths) >= min_matches
        return _result(
            ok,
            ctype,
            f"json any non-null match at {json_path}",
            {
                "glob": pattern,
                "jsonPath": json_path,
                "minMatches": min_matches,
                "matches": len(hit_paths),
                "matchPaths": hit_paths[:20],
            },
        )

    if ctype == "json_unique_count_at_least":
        pattern = str(check.get("glob", ""))
        json_path = str(check.get("jsonPath", ""))
        min_count = int(check.get("min", 1))
        matches = _glob_paths(repo_root, pattern)
        values: set[str] = set()
        for p in matches:
            if not p.is_file():
                continue
            try:
                payload = _load_json(p, json_cache)
            except Exception:
                continue
            found, value = _extract_json_path(payload, json_path)
            if found and value is not None:
                values.add(str(value))
        ok = len(values) >= min_count
        return _result(
            ok,
            ctype,
            f"json unique values >= {min_count} for {json_path}",
            {
                "glob": pattern,
                "jsonPath": json_path,
                "min": min_count,
                "uniqueCount": len(values),
                "values": sorted(values),
            },
        )

    return _result(False, "invalid", f"unsupported check type: {ctype}", {"check": check})


def _eval_check(check: dict[str, Any], *, repo_root: Path, json_cache: dict[Path, Any]) -> CheckResult:
    if "allOf" in check:
        children = [
            _eval_check(child, repo_root=repo_root, json_cache=json_cache)
            for child in list(check.get("allOf") or [])
            if isinstance(child, dict)
        ]
        ok = len(children) > 0 and all(child.ok for child in children)
        return _result(ok, "allOf", "all conditions must pass", children=children)

    if "anyOf" in check:
        children = [
            _eval_check(child, repo_root=repo_root, json_cache=json_cache)
            for child in list(check.get("anyOf") or [])
            if isinstance(child, dict)
        ]
        ok = len(children) > 0 and any(child.ok for child in children)
        return _result(ok, "anyOf", "at least one condition must pass", children=children)

    if "not" in check and isinstance(check.get("not"), dict):
        child = _eval_check(check["not"], repo_root=repo_root, json_cache=json_cache)
        ok = not child.ok
        return _result(ok, "not", "negated condition", children=[child])

    return _eval_leaf(check, repo_root=repo_root, json_cache=json_cache)


def _render_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# AMP+ Report")
    lines.append("")
    lines.append(f"- Generated: `{payload['generatedAtUtc']}`")
    lines.append(f"- Milestones file: `{payload['milestonesFile']}`")
    lines.append(f"- Score: **{payload['achievedPoints']}/{payload['totalPoints']}**")
    lines.append(f"- Remaining: **{payload['remainingPoints']}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| id | title | status | points |")
    lines.append("|---|---|---|---:|")
    for item in payload["items"]:
        status = "PASS" if item["pass"] else "FAIL"
        lines.append(f"| `{item['id']}` | {item['title']} | {status} | {item['points']} |")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    blockers = [item for item in payload["items"] if not item["pass"]]
    if not blockers:
        lines.append("- none")
    else:
        for item in blockers:
            failed = item.get("failedChecks", [])
            detail = failed[0]["message"] if failed else "check failed"
            lines.append(f"- `{item['id']}` {item['title']}: {detail}")
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    lines.append("- `project_eval_out_v2/evidence/`")
    lines.append("- `build_hw/**/bench_report.json`")
    lines.append("- `.github/workflows/tests.yml`")
    lines.append("- `docs/` + `tools/` + `benches/`")
    lines.append("")
    return "\n".join(lines) + "\n"


def score(milestones_path: Path, repo_root: Path) -> dict[str, Any]:
    data = json.loads(milestones_path.read_text(encoding="utf-8"))
    items_raw = data.get("items")
    if not isinstance(items_raw, list):
        raise ValueError("milestones file must contain a top-level 'items' list")

    json_cache: dict[Path, Any] = {}
    items_out: list[dict[str, Any]] = []
    total_points = 0
    achieved_points = 0

    for idx, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", f"ITEM-{idx+1:03d}"))
        title = str(raw.get("title", item_id))
        points = int(raw.get("points", 1))
        total_points += points
        checks = raw.get("checks")
        if not isinstance(checks, dict):
            result = _result(False, "invalid", "missing checks object")
        else:
            result = _eval_check(checks, repo_root=repo_root, json_cache=json_cache)

        passed = bool(result.ok)
        if passed:
            achieved_points += points

        failed = result.flatten_failed()
        passed_checks = result.flatten_passed()
        items_out.append(
            {
                "id": item_id,
                "title": title,
                "points": points,
                "pass": passed,
                "description": raw.get("description"),
                "checkResult": result.to_dict(),
                "failedChecks": [
                    {"kind": x.kind, "message": x.message, "details": x.details}
                    for x in failed
                ],
                "passedChecks": [
                    {"kind": x.kind, "message": x.message, "details": x.details}
                    for x in passed_checks[:20]
                ],
            }
        )

    remaining = total_points - achieved_points
    payload = {
        "generatedAtUtc": _utc_now(),
        "milestonesFile": str(milestones_path if milestones_path.is_absolute() else milestones_path),
        "version": data.get("version"),
        "description": data.get("description"),
        "totalPoints": total_points,
        "achievedPoints": achieved_points,
        "remainingPoints": remaining,
        "passRate": round((achieved_points / total_points), 6) if total_points else 0.0,
        "allPassed": remaining == 0,
        "items": items_out,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="score_milestones.py", description="Score milestone checklists from repo evidence")
    parser.add_argument("--milestones", type=Path, required=True, help="Milestones JSON definition")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root (default: .)")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("project_eval_out_v2/AMP_PLUS_SCOREBOARD.json"),
        help="Output JSON scoreboard path",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("project_eval_out_v2/AMP_PLUS_REPORT.md"),
        help="Output markdown report path",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    milestones_path = args.milestones if args.milestones.is_absolute() else (repo_root / args.milestones)
    payload = score(milestones_path, repo_root)
    report_md = _render_report(payload)

    out_json = args.out_json if args.out_json.is_absolute() else (repo_root / args.out_json)
    out_md = args.out_md if args.out_md.is_absolute() else (repo_root / args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(report_md, encoding="utf-8")

    print(json.dumps({"ok": True, "scoreboard": str(out_json), "report": str(out_md)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
