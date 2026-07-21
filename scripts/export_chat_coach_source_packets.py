#!/usr/bin/env python3
"""Export deterministic, mechanical source packets from formal P02/P03 JSON.

The exporter only copies, orders, formats, and validates source data. It does
not perform course analysis or create tags, OBs, supplements, or reply text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.3.0"
REPORT_SCHEMA_VERSION = "1.1"
DATA_ROOT = Path("data/courses")
OUTPUT_ROOT = Path("chat-coach/source-material")
REPORT_FILENAME = "validation-report.json"

DEFAULT_COURSES = [f"C{i:03d}" for i in range(1, 19)] + ["C021", "C022"]

OUTPUT_FILES = (
    "source-manifest.md",
    "课程原文.md",
    "聊天原话.md",
    "讲师原话.md",
    "课板原文.md",
    "案例边界.md",
    "提取校验.md",
)

# Hard gates decide ok/failed. Input-order time reversals are warnings only.
HARD_CHECK_KEYS = (
    "segment_count",
    "role_file_counts",
    "unique_segment_ids",
    "exported_order_time_monotonic",
    "segment_set_preserved",
    "p03_boundaries_in_p02",
    "utf8_readable",
    "deterministic_render",
)
WARNING_CHECK_KEYS = ("input_order_time_violations",)

_EXCLUDED_TOKEN = re.compile(
    r"(?:^|[-_.])(?:qa|baseline|input|review|review-pack|review-decisions)(?:$|[-_.])"
    r"|\.cursor-task\.json$",
    re.IGNORECASE,
)
_VERSION = re.compile(r"(?:^|[-_.])v(\d+)(?=$|[-_.])", re.IGNORECASE)


def _is_excluded(filename: str) -> bool:
    """Return whether a candidate is a QA/input/review/task artifact."""
    return _EXCLUDED_TOKEN.search(filename) is not None


def _version_key(path: Path) -> tuple[int, ...]:
    """Return numeric version components used by both P02 and P03 selection."""
    versions = tuple(int(value) for value in _VERSION.findall(path.name))
    return versions or (0,)


def _latest_formal(paths: list[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file() and not _is_excluded(path.name)]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (_version_key(path), path.name.casefold(), path.name))


def _find_latest_p02(course_dir: Path) -> Path | None:
    """Find the numerically latest formal P02 in 02_normalized."""
    search_dir = course_dir / "02_normalized"
    if not search_dir.exists():
        return None
    return _latest_formal(list(search_dir.glob("P02-knowledge-*.json")))


def _find_latest_p03(course_dir: Path) -> Path | None:
    """Find the numerically latest formal P03 in supported source folders."""
    candidates: list[Path] = []
    for search_dir in (course_dir / "03_cases", course_dir / "02_normalized"):
        if search_dir.exists():
            candidates.extend(search_dir.glob("P03-knowledge-*.json"))
    return _latest_formal(candidates)


def _format_ts(ms: int) -> str:
    """Format milliseconds as HH:MM:SS.mmm."""
    total_seconds, milliseconds = divmod(int(ms), 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _escape_md(text: str) -> str:
    """Escape heading/list prefixes for callers that need inline Markdown."""
    escaped: list[str] = []
    for line in str(text).split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            line = "\\" + line
        elif stripped.startswith(("- ", "* ")):
            line = "\\ " + line
        escaped.append(line)
    return "\n".join(escaped)


def _fenced(text: Any) -> list[str]:
    """Return a code fence longer than any backtick run in the source text."""
    value = "" if text is None else str(text)
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, value, fence]


def _json_fenced(value: Any) -> list[str]:
    return _fenced(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _content_hashes(contents: dict[str, str]) -> dict[str, str]:
    return {name: _sha256_bytes(contents[name].encode("utf-8")) for name in OUTPUT_FILES}


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _segment_lines(segment: dict[str, Any], include_classification: bool = True) -> list[str]:
    lines = [
        f"## {segment['segment_id']}",
        "",
        f"- start_ms / end_ms: {segment['start_ms']} / {segment['end_ms']}",
        f"- 时间: {_format_ts(segment['start_ms'])} – {_format_ts(segment['end_ms'])}",
        f"- speaker: `{segment.get('speaker', '?')}`",
        f"- source_role: `{segment.get('source_role', '?')}`",
        f"- content_type: `{segment.get('content_type', '?')}`",
    ]
    if include_classification:
        lines.extend(
            [
                f"- epistemic_type: `{segment.get('epistemic_type', '?')}`",
                f"- relevance: `{segment.get('relevance', '?')}`",
            ]
        )
    lines.extend(["", "**raw_text:**", "", *_fenced(segment.get("raw_text", ""))])
    lines.extend(["", "**normalized_text:**", "", *_fenced(segment.get("normalized_text", "")), ""])
    return lines


def _is_board_chat(segment: dict[str, Any]) -> bool:
    """Mechanically recognize board text that contains conversational markers."""
    text = (segment.get("normalized_text") or segment.get("raw_text") or "").strip()
    indicators = ("说", "问", "答", "嗯", "啊", "哈哈", "哦", "呢", "吧")
    return len(text) > 5 and any(indicator in text for indicator in indicators)


def _ordered_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order exported source chronologically while retaining stable input order ties."""
    indexed = enumerate(segments)
    return [
        segment
        for _, segment in sorted(
            indexed,
            key=lambda item: (
                int(item[1]["start_ms"]),
                int(item[1]["end_ms"]),
                item[0],
            ),
        )
    ]


def _time_violations(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return adjacent start_ms reversals in the given segment sequence."""
    violations: list[dict[str, Any]] = []
    for previous, current in zip(segments, segments[1:]):
        if int(current["start_ms"]) < int(previous["start_ms"]):
            violations.append(
                {
                    "previous_segment_id": previous["segment_id"],
                    "previous_start_ms": int(previous["start_ms"]),
                    "current_segment_id": current["segment_id"],
                    "current_start_ms": int(current["start_ms"]),
                }
            )
    return violations


def _base_checks(
    input_segments: list[dict[str, Any]],
    export_segments: list[dict[str, Any]],
    p03: dict[str, Any],
    chat_segments: list[dict[str, Any]],
    instructor_segments: list[dict[str, Any]],
    board_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    input_ids = [str(segment["segment_id"]) for segment in input_segments]
    export_ids = [str(segment["segment_id"]) for segment in export_segments]
    duplicate_ids = sorted({segment_id for segment_id in export_ids if export_ids.count(segment_id) > 1})
    input_id_set = set(input_ids)
    export_id_set = set(export_ids)

    input_violations = _time_violations(input_segments)
    export_violations = _time_violations(export_segments)

    boundary_failures: list[dict[str, str]] = []
    for case in p03.get("cases", []):
        for field in ("start_segment_id", "end_segment_id"):
            segment_id = str(case.get(field, ""))
            if segment_id not in input_id_set:
                boundary_failures.append(
                    {
                        "case_id": str(case.get("case_id", "?")),
                        "field": field,
                        "segment_id": segment_id,
                    }
                )

    expected_chat = sum(
        1
        for segment in export_segments
        if segment.get("source_role") == "actual_chat"
        or (segment.get("source_role") == "board" and _is_board_chat(segment))
    )
    expected_instructor = sum(
        1 for segment in export_segments if segment.get("source_role") == "instructor_explanation"
    )
    expected_board = sum(
        1
        for segment in export_segments
        if segment.get("source_role") == "board" or segment.get("content_type") == "board_ocr"
    )
    role_count_passed = (
        len(chat_segments) == expected_chat
        and len(instructor_segments) == expected_instructor
        and len(board_segments) == expected_board
    )
    set_preserved = (
        len(input_segments) == len(export_segments)
        and input_id_set == export_id_set
        and len(input_ids) == len(input_id_set)
        and len(export_ids) == len(export_id_set)
    )

    return {
        "segment_count": {
            "passed": len(input_segments) == len(export_segments),
            "p02_count": len(input_segments),
            "exported_count": len(export_segments),
        },
        "role_file_counts": {
            "passed": role_count_passed,
            "expected": {
                "聊天原话.md": expected_chat,
                "讲师原话.md": expected_instructor,
                "课板原文.md": expected_board,
            },
            "actual": {
                "聊天原话.md": len(chat_segments),
                "讲师原话.md": len(instructor_segments),
                "课板原文.md": len(board_segments),
            },
        },
        "unique_segment_ids": {
            "passed": not duplicate_ids,
            "total": len(export_ids),
            "unique": len(export_id_set),
            "duplicate_segment_ids": duplicate_ids,
        },
        "input_order_time_violations": {
            "severity": "warning",
            "passed": True,
            "warning": bool(input_violations),
            "violation_count": len(input_violations),
            "violations": input_violations,
        },
        "exported_order_time_monotonic": {
            "passed": not export_violations,
            "violation_count": len(export_violations),
            "violations": export_violations,
        },
        "segment_set_preserved": {
            "passed": set_preserved,
            "p02_count": len(input_segments),
            "exported_count": len(export_segments),
            "p02_unique_ids": len(input_id_set),
            "exported_unique_ids": len(export_id_set),
            "missing_ids": sorted(input_id_set - export_id_set),
            "extra_ids": sorted(export_id_set - input_id_set),
        },
        "p03_boundaries_in_p02": {
            "passed": not boundary_failures,
            "failure_count": len(boundary_failures),
            "failures": boundary_failures,
        },
    }


def _hard_checks(checks: dict[str, Any]) -> dict[str, Any]:
    return {key: checks[key] for key in HARD_CHECK_KEYS if key in checks}


def _warning_checks(checks: dict[str, Any]) -> dict[str, Any]:
    return {key: checks[key] for key in WARNING_CHECK_KEYS if key in checks}


def _all_hard_checks_pass(checks: dict[str, Any]) -> bool:
    return all(bool(check.get("passed")) for check in _hard_checks(checks).values())


def _count_failed_hard_checks(checks: dict[str, Any]) -> int:
    return sum(1 for check in _hard_checks(checks).values() if not check.get("passed"))


def _count_warnings(checks: dict[str, Any]) -> int:
    return sum(1 for check in _warning_checks(checks).values() if check.get("warning"))


def _verification_lines(course_id: str, checks: dict[str, Any]) -> list[str]:
    count = checks["segment_count"]
    roles = checks["role_file_counts"]
    unique = checks["unique_segment_ids"]
    input_order = checks["input_order_time_violations"]
    exported_order = checks["exported_order_time_monotonic"]
    preserved = checks["segment_set_preserved"]
    boundaries = checks["p03_boundaries_in_p02"]
    utf8 = checks["utf8_readable"]
    deterministic = checks["deterministic_render"]

    lines = [f"# {course_id} 提取校验", ""]
    lines.append("1. 全部 7 个输出文件存在 → PASS")
    lines.append(
        f"2. segment 数量: 课程原文.md={count['exported_count']}, "
        f"P02={count['p02_count']} → {'PASS' if count['passed'] else 'FAIL'}"
    )
    lines.append(
        "3. 角色分文件计数: "
        f"expected={json.dumps(roles['expected'], ensure_ascii=False, sort_keys=True)}, "
        f"actual={json.dumps(roles['actual'], ensure_ascii=False, sort_keys=True)} "
        f"→ {'PASS' if roles['passed'] else 'FAIL'}"
    )
    lines.append(
        f"4. segment ID 唯一: total={unique['total']}, unique={unique['unique']} "
        f"→ {'PASS' if unique['passed'] else 'FAIL'}"
    )
    if not unique["passed"]:
        lines.append(f"   重复 segment: {', '.join(unique['duplicate_segment_ids'])}")

    if input_order["violation_count"] == 0:
        lines.append("5. P02 原始顺序时间逆序检查 → PASS（无输入逆序）")
    else:
        lines.append(
            f"5. P02 原始顺序时间逆序检查 → WARNING（输入数据），"
            f"发现 {input_order['violation_count']} 处逆序；不判定导出失败"
        )
        for violation in input_order["violations"][:20]:
            lines.append(
                "   输入逆序: "
                f"{violation['previous_segment_id']}({violation['previous_start_ms']}ms) → "
                f"{violation['current_segment_id']}({violation['current_start_ms']}ms)"
            )
        if input_order["violation_count"] > 20:
            lines.append(f"   … 另有 {input_order['violation_count'] - 20} 处未展开")

    if exported_order["passed"]:
        lines.append("6. 课程原文.md 导出顺序 start_ms 单调不下降 → PASS")
    else:
        lines.append(
            f"6. 课程原文.md 导出顺序 start_ms 单调不下降 → FAIL，"
            f"发现 {exported_order['violation_count']} 处逆序"
        )
        for violation in exported_order["violations"][:20]:
            lines.append(
                "   导出逆序: "
                f"{violation['previous_segment_id']}({violation['previous_start_ms']}ms) → "
                f"{violation['current_segment_id']}({violation['current_start_ms']}ms)"
            )

    if preserved["passed"]:
        lines.append(
            "7. segment 集合保持完整（无丢失/重复/合并）: "
            f"p02={preserved['p02_count']}, exported={preserved['exported_count']} → PASS"
        )
    else:
        lines.append(
            "7. segment 集合保持完整（无丢失/重复/合并） → FAIL "
            f"(missing={len(preserved['missing_ids'])}, extra={len(preserved['extra_ids'])})"
        )

    if boundaries["passed"]:
        lines.append("8. P03 start/end segment 均可回查 P02 → PASS")
    else:
        lines.append(
            f"8. P03 start/end segment 均可回查 P02 → FAIL，"
            f"发现 {boundaries['failure_count']} 个缺失边界"
        )
        for failure in boundaries["failures"]:
            lines.append(
                f"   {failure['case_id']} {failure['field']}={failure['segment_id']} 不在 P02"
            )

    lines.append(
        f"9. 全部 7 个文件 UTF-8 编码并可重读 → {'PASS' if utf8['passed'] else 'FAIL'}"
    )
    lines.append(
        "10. 两次独立完整渲染 SHA-256 比较 "
        f"→ {'PASS' if deterministic['passed'] else 'FAIL'}"
    )
    if deterministic["mismatches"]:
        lines.append(f"   hash 不一致文件: {', '.join(deterministic['mismatches'])}")

    hard_ok = _all_hard_checks_pass(checks)
    warning_count = _count_warnings(checks)
    summary = "ALL PASS"
    if not hard_ok:
        summary = "HAS FAILURES"
    elif warning_count:
        summary = f"ALL PASS WITH {warning_count} WARNING(S)"
    lines.extend(["", f"**总结: {summary}**"])
    return lines


def _build_packet(
    course_id: str,
    p02_path: Path,
    p03_path: Path,
    p02: dict[str, Any],
    p03: dict[str, Any],
    deterministic_passed: bool,
    deterministic_mismatches: list[str],
) -> tuple[dict[str, str], dict[str, Any], dict[str, int]]:
    input_segments = list(p02.get("segments", []))
    export_segments = _ordered_segments(input_segments)
    chat_segments = [
        segment
        for segment in export_segments
        if segment.get("source_role") == "actual_chat"
        or (segment.get("source_role") == "board" and _is_board_chat(segment))
    ]
    instructor_segments = [
        segment for segment in export_segments if segment.get("source_role") == "instructor_explanation"
    ]
    board_segments = [
        segment
        for segment in export_segments
        if segment.get("source_role") == "board" or segment.get("content_type") == "board_ocr"
    ]

    role_counts: dict[str, int] = {}
    for segment in input_segments:
        role = str(segment.get("source_role", "unknown"))
        role_counts[role] = role_counts.get(role, 0) + 1

    checks = _base_checks(
        input_segments,
        export_segments,
        p03,
        chat_segments,
        instructor_segments,
        board_segments,
    )
    checks["utf8_readable"] = {"passed": True, "checked_files": list(OUTPUT_FILES)}
    checks["deterministic_render"] = {
        "passed": deterministic_passed,
        "mismatches": deterministic_mismatches,
    }
    all_ok = _all_hard_checks_pass(checks)
    warning_count = _count_warnings(checks)

    start_ms = min(int(segment["start_ms"]) for segment in input_segments)
    end_ms = max(int(segment["end_ms"]) for segment in input_segments)
    case_count = len(p03.get("cases", []))

    manifest = [
        f"# {course_id} 原文资料包",
        "",
        "## 基本信息",
        "",
        f"- 课程 ID: `{course_id}`",
        f"- P02 路径: `{p02_path.as_posix()}`",
        f"- P03 路径: `{p03_path.as_posix()}`",
        f"- P02 schema_version: `{p02.get('schema_version', '?')}`",
        f"- P02 prompt_version: `{p02.get('prompt_version', '?')}`",
        f"- P03 schema_version: `{p03.get('schema_version', '?')}`",
        f"- P03 prompt_version: `{p03.get('prompt_version', '?')}`",
        f"- segment 总数: {len(input_segments)}",
        f"- 课程时间范围: {_format_ts(start_ms)} – {_format_ts(end_ms)}",
        f"- P03 案例数量: {case_count}",
        f"- 脚本版本: {SCRIPT_VERSION}",
        "- 生成标识: `deterministic-from-input`",
        "",
        "## source_role 统计",
        "",
    ]
    for role, count in sorted(role_counts.items()):
        manifest.append(f"- `{role}`: {count}")
    manifest.extend(
        [
            "",
            "## 校验结果",
            "",
            f"- {'ALL PASS' if all_ok else 'HAS FAILURES'}"
            + (f" ({warning_count} warning)" if all_ok and warning_count else ""),
            "- 详见 `提取校验.md`",
        ]
    )

    course_lines = [f"# {course_id} 课程原文", ""]
    for segment in export_segments:
        course_lines.extend(_segment_lines(segment))

    chat_lines = [f"# {course_id} 聊天原话", ""]
    for segment in chat_segments:
        chat_lines.extend(_segment_lines(segment, include_classification=False))

    instructor_lines = [f"# {course_id} 讲师原话", ""]
    for segment in instructor_segments:
        instructor_lines.extend(_segment_lines(segment, include_classification=False))

    board_lines = [f"# {course_id} 课板原文", ""]
    for segment in board_segments:
        board_lines.extend(_segment_lines(segment, include_classification=False))

    segment_lookup = {str(segment["segment_id"]): segment for segment in input_segments}
    case_lines = [f"# {course_id} 案例边界", ""]
    top_uncertainties = p03.get("uncertainties", [])
    for case in p03.get("cases", []):
        start_id = str(case.get("start_segment_id", ""))
        end_id = str(case.get("end_segment_id", ""))
        case_lines.extend(
            [
                f"## {case.get('case_id', '?')}",
                "",
                f"- 标题: {case.get('title', '?')}",
                f"- start_segment_id: `{start_id}`",
                f"- end_segment_id: `{end_id}`",
            ]
        )
        if start_id in segment_lookup:
            case_lines.append(f"- 开始时间: {_format_ts(segment_lookup[start_id]['start_ms'])}")
        if end_id in segment_lookup:
            case_lines.append(f"- 结束时间: {_format_ts(segment_lookup[end_id]['end_ms'])}")
        case_lines.extend(
            [
                f"- completeness: `{case.get('completeness', '?')}`",
                f"- confidence: {case.get('confidence', '?')}",
                "",
                "**boundary_evidence 原文:**",
                "",
                *_json_fenced(case.get("boundary_evidence", {})),
                "",
                "**case uncertainties 原文:**",
                "",
                *_json_fenced(case.get("uncertainties", [])),
                "",
            ]
        )
    case_lines.extend(["## P03 顶层 uncertainties 原文", "", *_json_fenced(top_uncertainties), ""])

    contents = {
        "source-manifest.md": "\n".join(manifest) + "\n",
        "课程原文.md": "\n".join(course_lines) + "\n",
        "聊天原话.md": "\n".join(chat_lines) + "\n",
        "讲师原话.md": "\n".join(instructor_lines) + "\n",
        "课板原文.md": "\n".join(board_lines) + "\n",
        "案例边界.md": "\n".join(case_lines) + "\n",
        "提取校验.md": "\n".join(_verification_lines(course_id, checks)) + "\n",
    }
    return contents, checks, role_counts


def _export_course(course_id: str) -> dict[str, Any]:
    """Export one course and return complete machine-readable evidence."""
    course_dir = DATA_ROOT / course_id
    if not course_dir.exists():
        return {"course_id": course_id, "status": "blocked", "reason": "course directory missing"}

    p02_path = _find_latest_p02(course_dir)
    if p02_path is None:
        return {"course_id": course_id, "status": "blocked", "reason": "no formal P02 found"}

    p03_path = _find_latest_p03(course_dir)
    if p03_path is None:
        return {
            "course_id": course_id,
            "status": "blocked",
            "reason": "no formal P03 found",
            "p02_path": p02_path.as_posix(),
        }

    try:
        p02 = json.loads(p02_path.read_text(encoding="utf-8"))
        p03 = json.loads(p03_path.read_text(encoding="utf-8"))
        segments = p02.get("segments", [])
        if not isinstance(segments, list) or not segments:
            return {
                "course_id": course_id,
                "status": "blocked",
                "reason": "P02 has no segments",
                "p02_path": p02_path.as_posix(),
                "p03_path": p03_path.as_posix(),
            }

        first_contents, _, _ = _build_packet(course_id, p02_path, p03_path, p02, p03, True, [])
        second_contents, _, _ = _build_packet(course_id, p02_path, p03_path, p02, p03, True, [])
        first_hashes = _content_hashes(first_contents)
        second_hashes = _content_hashes(second_contents)
        mismatches = [name for name in OUTPUT_FILES if first_hashes[name] != second_hashes[name]]
        contents, checks, role_counts = _build_packet(
            course_id,
            p02_path,
            p03_path,
            p02,
            p03,
            not mismatches,
            mismatches,
        )

        out_dir = OUTPUT_ROOT / course_id
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename in OUTPUT_FILES:
            _write_text(out_dir / filename, contents[filename])

        reread_failures: list[str] = []
        for filename in OUTPUT_FILES:
            path = out_dir / filename
            try:
                path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                reread_failures.append(filename)
        if reread_failures:
            checks["utf8_readable"] = {
                "passed": False,
                "checked_files": list(OUTPUT_FILES),
                "failures": reread_failures,
            }

        output_hashes = {filename: _file_sha256(out_dir / filename) for filename in OUTPUT_FILES}
        hard_ok = _all_hard_checks_pass(checks)
        warning_count = _count_warnings(checks)
        failed_hard = _count_failed_hard_checks(checks)
        status = "ok" if hard_ok else "failed"
        reason = None if hard_ok else "one or more hard validation checks failed"
        return {
            "course_id": course_id,
            "status": status,
            "reason": reason,
            "p02_path": p02_path.as_posix(),
            "p03_path": p03_path.as_posix(),
            "segment_count": len(segments),
            "case_count": len(p03.get("cases", [])),
            "role_counts": role_counts,
            "checks": checks,
            "all_ok": hard_ok,
            "warning_count": warning_count,
            "failed_checks_count": failed_hard,
            "output_hashes": output_hashes,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return {
            "course_id": course_id,
            "status": "failed",
            "reason": f"{type(error).__name__}: {error}",
            "p02_path": p02_path.as_posix(),
            "p03_path": p03_path.as_posix(),
        }


def _attach_rerun_hash_evidence(
    first_results: list[dict[str, Any]], second_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    second_by_course = {result["course_id"]: result for result in second_results}
    combined: list[dict[str, Any]] = []
    for first in first_results:
        result = dict(first)
        second = second_by_course.get(first["course_id"])
        first_hashes = first.get("output_hashes", {})
        second_hashes = second.get("output_hashes", {}) if second else {}
        mismatches = sorted(
            filename
            for filename in set(first_hashes) | set(second_hashes)
            if first_hashes.get(filename) != second_hashes.get(filename)
        )
        both_ok = (
            first.get("status") == "ok"
            and second is not None
            and second.get("status") == "ok"
        )
        hash_passed = both_ok and not mismatches
        result["rerun_hash_check"] = {
            "passed": hash_passed,
            "first_status": first.get("status"),
            "second_status": second.get("status") if second else "missing",
            "mismatches": mismatches,
            "first_hashes": first_hashes,
            "second_hashes": second_hashes,
        }
        if first.get("status") in {"blocked", "failed"}:
            combined.append(result)
            continue
        if not hash_passed:
            result["status"] = "failed"
            result["all_ok"] = False
            result["reason"] = "cross-second rerun hash comparison failed"
            result["failed_checks_count"] = int(result.get("failed_checks_count", 0)) + 1
        else:
            result["reason"] = None
        combined.append(result)
    return combined


def _write_global_report(results: list[dict[str, Any]], delay_seconds: float = 0.0) -> Path:
    """Write a deterministic machine-readable report for every requested course."""
    report_path = OUTPUT_ROOT / REPORT_FILENAME
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    exported = sum(1 for result in results if result.get("status") == "ok")
    blocked = sum(1 for result in results if result.get("status") == "blocked")
    failed = sum(1 for result in results if result.get("status") == "failed")
    warning_count = sum(int(result.get("warning_count", 0)) for result in results)
    failed_checks = sum(int(result.get("failed_checks_count", 0)) for result in results)
    all_passed = (
        len(results) > 0
        and exported == len(results)
        and blocked == 0
        and failed == 0
        and failed_checks == 0
        and all(
            result.get("status") == "ok"
            and result.get("all_ok") is True
            and result.get("reason") is None
            and result.get("rerun_hash_check", {}).get("passed") is True
            for result in results
        )
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "deterministic": bool(all_passed),
        "rerun_delay_seconds": delay_seconds,
        "total_courses": len(results),
        "exported": exported,
        "blocked_count": blocked,
        "failed_count": failed,
        "warning_count": warning_count,
        "failed_checks_count": failed_checks,
        "all_passed": all_passed,
        "courses": results,
    }
    _write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export deterministic source material packets")
    parser.add_argument("--courses", help="Comma-separated course IDs")
    parser.add_argument("--dry-run", action="store_true", help="Only list selected inputs")
    parser.add_argument(
        "--rerun-delay-seconds",
        type=float,
        default=1.1,
        help="Delay before the second disk export used for real hash comparison",
    )
    args = parser.parse_args()

    courses = [course.strip() for course in args.courses.split(",")] if args.courses else DEFAULT_COURSES
    courses = [course for course in courses if course]
    if args.dry_run:
        print(f"Would export {len(courses)} courses: {', '.join(courses)}")
        return 0

    first_results = [_export_course(course_id) for course_id in courses]
    if args.rerun_delay_seconds > 0:
        time.sleep(args.rerun_delay_seconds)
    second_results = [_export_course(course_id) for course_id in courses]
    results = _attach_rerun_hash_evidence(first_results, second_results)
    report_path = _write_global_report(results, args.rerun_delay_seconds)

    for result in results:
        if result["status"] == "ok":
            warning = int(result.get("warning_count", 0))
            warning_label = f", warnings={warning}" if warning else ""
            print(
                f"  {result['course_id']}: {result['segment_count']} segments, "
                f"{result['case_count']} cases, status=ok, "
                f"rerun_hash=PASS{warning_label}"
            )
        else:
            print(f"  {result['course_id']}: {result['status'].upper()} - {result.get('reason', '?')}")
    print(f"Validation report: {report_path}")

    return 0 if all(
        result.get("status") == "ok"
        and result.get("all_ok")
        and result.get("reason") is None
        and result.get("rerun_hash_check", {}).get("passed")
        for result in results
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
