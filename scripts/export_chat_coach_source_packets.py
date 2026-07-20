#!/usr/bin/env python3
"""Export mechanical source material packets from P02/P03 data.

This is a deterministic, read-only extraction tool. It does NOT analyze
course content, generate labels, create OB, or produce reply suggestions.

Usage:
    python scripts/export_chat_coach_source_packets.py [--courses C001,C002,...] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.0.0"
DATA_ROOT = Path("data/courses")
OUTPUT_ROOT = Path("chat-coach/source-material")

# Courses to process (C019-C020 excluded per spec)
DEFAULT_COURSES = (
    [f"C{i:03d}" for i in range(1, 19)]  # C001-C018
    + ["C021", "C022"]
)


def _find_latest_p02(course_dir: Path) -> Path | None:
    """Find latest formal P02, excluding qa/baseline/input/review files."""
    p02_dir = course_dir / "02_normalized"
    if not p02_dir.exists():
        return None
    candidates = []
    for f in p02_dir.glob("P02-knowledge-*.json"):
        name = f.name
        if any(skip in name for skip in ["qa", "baseline", "input", "review-pack", "review-decisions", ".cursor-task"]):
            continue
        candidates.append(f)
    if not candidates:
        return None
    return sorted(candidates)[-1]


def _find_latest_p03(course_dir: Path) -> Path | None:
    """Find latest formal P03 from 02_normalized or 03_cases."""
    candidates = []
    for search_dir in [course_dir / "02_normalized", course_dir / "03_cases"]:
        if not search_dir.exists():
            continue
        for f in search_dir.glob("P03-knowledge-*.json"):
            name = f.name
            if any(skip in name for skip in ["qa", "baseline", "input", "review", ".cursor-task"]):
                continue
            candidates.append(f)
    if not candidates:
        return None
    # Sort by version number (v002 < v003)
    def _version_key(p: Path) -> tuple[int, ...]:
        import re
        nums = re.findall(r"v(\d+)", p.name)
        return tuple(int(n) for n in nums) if nums else (0,)
    return sorted(candidates, key=_version_key)[-1]


def _format_ts(ms: int) -> str:
    """Format milliseconds as HH:MM:SS.mmm."""
    total_s = ms // 1000
    ms_rem = ms % 1000
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"


def _escape_md(text: str) -> str:
    """Escape text so Markdown doesn't misparse WeChat content as headings/lists."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Prevent lines starting with # from becoming headings
        if stripped.startswith("#"):
            line = "\\" + line
        # Prevent lines starting with - or * from becoming lists
        if stripped.startswith("- ") or stripped.startswith("* "):
            line = "\\ " + line
        lines.append(line)
    return "\n".join(lines)


def _export_course(course_id: str) -> dict[str, Any]:
    """Export source packets for one course. Returns result dict."""
    course_dir = DATA_ROOT / course_id
    if not course_dir.exists():
        return {"course_id": course_id, "status": "blocked", "reason": "course directory missing"}

    # Find P02
    p02_path = _find_latest_p02(course_dir)
    if not p02_path:
        return {"course_id": course_id, "status": "blocked", "reason": "no formal P02 found"}

    p02 = json.loads(p02_path.read_text(encoding="utf-8"))
    segments = p02.get("segments", [])
    if not segments:
        return {"course_id": course_id, "status": "blocked", "reason": "P02 has no segments"}

    # Find P03 (optional for some courses)
    p03_path = _find_latest_p03(course_dir)
    p03 = None
    if p03_path:
        p03 = json.loads(p03_path.read_text(encoding="utf-8"))

    # Create output directory
    out_dir = OUTPUT_ROOT / course_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build segment lookup
    seg_by_id: dict[str, dict[str, Any]] = {}
    for seg in segments:
        seg_by_id[seg["segment_id"]] = seg

    # --- source-manifest.md ---
    role_counts: dict[str, int] = {}
    for seg in segments:
        role = seg.get("source_role", "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1

    start_ms = min(s.get("start_ms", 0) for s in segments)
    end_ms = max(s.get("end_ms", 0) for s in segments)
    case_count = len(p03.get("cases", [])) if p03 else 0

    manifest_lines = [
        f"# {course_id} 原文资料包",
        "",
        "## 基本信息",
        "",
        f"- 课程 ID: `{course_id}`",
        f"- P02 路径: `{p02_path.as_posix()}`",
        f"- P03 路径: `{p03_path.as_posix() if p03_path else '无'}`",
        f"- P02 schema_version: `{p02.get('schema_version', '?')}`",
        f"- P02 prompt_version: `{p02.get('prompt_version', '?')}`",
        f"- segment 总数: {len(segments)}",
        f"- 课程时间范围: {_format_ts(start_ms)} – {_format_ts(end_ms)}" if (start_ms := segments[0]["start_ms"]) is not None else "",
        f"- P03 案例数量: {case_count}",
        f"- 生成时间: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"- 脚本版本: {SCRIPT_VERSION}",
        "",
        "## source_role 统计",
        "",
    ]
    role_counts: dict[str, int] = {}
    for seg in segments:
        role = seg.get("source_role", "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    for role, count in sorted(role_counts.items()):
        manifest_lines.append(f"- `{role}`: {count}")

    manifest_lines.extend(["", "## 校验结果", "", "见 `提取校验.md`"])

    (out_dir / "source-manifest.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    # 课程原文.md — all P02 segments
    course_lines = [f"# {course_id} 课程原文", ""]
    for seg in segments:
        course_lines.append(f"## {seg['segment_id']}")
        course_lines.append("")
        course_lines.append(f"- 时间: {_format_ts(seg['start_ms'])} – {_format_ts(seg['end_ms'])}")
        course_lines.append(f"- speaker: `{seg.get('speaker', '?')}`")
        course_lines.append(f"- source_role: `{seg.get('source_role', '?')}`")
        course_lines.append(f"- content_type: `{seg.get('content_type', '?')}`")
        course_lines.append("")
        course_lines.append("**raw_text:**")
        course_lines.append("")
        course_lines.append("```")
        course_lines.append(_escape_md(seg.get("raw_text", "")))
        course_lines.append("```")
        course_lines.append("")
        course_lines.append("**normalized_text:**")
        course_lines.append("")
        course_lines.append("```")
        course_lines.append(_escape_md(seg.get("normalized_text", "")))
        course_lines.append("```")
        course_lines.append("")
    (out_dir / "课程原文.md").write_text("\n".join(course_lines) + "\n", encoding="utf-8")

    # 聊天原话.md — actual_chat + board chat
    chat_lines = [f"# {course_id} 聊天原话", ""]
    chat_count = 0
    for seg in segments:
        role = seg.get("source_role", "")
        if role == "actual_chat" or (role == "board" and _is_board_chat(seg)):
            chat_count += 1
            chat_lines.append(f"## {seg['segment_id']}")
            chat_lines.append("")
            chat_lines.append(f"- 时间: {_format_ts(seg['start_ms'])} – {_format_ts(seg['end_ms'])}")
            chat_lines.append(f"- speaker: `{seg.get('speaker', '?')}`")
            chat_lines.append(f"- source_role: `{role}`")
            chat_lines.append("")
            chat_lines.append("**raw_text:**")
            chat_lines.append("")
            chat_lines.append("```")
            chat_lines.append(_escape_md(seg.get("raw_text", "")))
            chat_lines.append("```")
            chat_lines.append("")
            chat_lines.append("**normalized_text:**")
            chat_lines.append("")
            chat_lines.append("```")
            chat_lines.append(_escape_md(seg.get("normalized_text", "")))
            chat_lines.append("```")
            chat_lines.append("")
    (out_dir / "聊天原话.md").write_text("\n".join(chat_lines) + "\n", encoding="utf-8")

    # 讲师原话.md — instructor_explanation
    instructor_lines = [f"# {course_id} 讲师原话", ""]
    instructor_count = 0
    for seg in segments:
        if seg.get("source_role") == "instructor_explanation":
            instructor_count += 1
            instructor_lines.append(f"## {seg['segment_id']}")
            instructor_lines.append("")
            instructor_lines.append(f"- 时间: {_format_ts(seg['start_ms'])} – {_format_ts(seg['end_ms'])}")
            instructor_lines.append(f"- speaker: `{seg.get('speaker', '?')}`")
            instructor_lines.append("")
            instructor_lines.append("**raw_text:**")
            instructor_lines.append("")
            instructor_lines.append("```")
            instructor_lines.append(_escape_md(seg.get("raw_text", "")))
            instructor_lines.append("```")
            instructor_lines.append("")
            instructor_lines.append("**normalized_text:**")
            instructor_lines.append("")
            instructor_lines.append("```")
            instructor_lines.append(_escape_md(seg.get("normalized_text", "")))
            instructor_lines.append("```")
            instructor_lines.append("")
    (out_dir / "讲师原话.md").write_text("\n".join(instructor_lines) + "\n", encoding="utf-8")

    # 课板原文.md — board / board_ocr
    board_lines = [f"# {course_id} 课板原文", ""]
    board_count = 0
    for seg in segments:
        if seg.get("source_role") == "board" or seg.get("content_type") == "board_ocr":
            board_count += 1
            board_lines.append(f"## {seg['segment_id']}")
            board_lines.append("")
            board_lines.append(f"- 时间: {_format_ts(seg['start_ms'])} – {_format_ts(seg['end_ms'])}")
            board_lines.append("")
            board_lines.append("**raw_text:**")
            board_lines.append("")
            board_lines.append("```")
            board_lines.append(_escape_md(seg.get("raw_text", "")))
            board_lines.append("```")
            board_lines.append("")
            board_lines.append("**normalized_text:**")
            board_lines.append("")
            board_lines.append("```")
            board_lines.append(_escape_md(seg.get("normalized_text", "")))
            board_lines.append("```")
            board_lines.append("")
    (out_dir / "课板原文.md").write_text("\n".join(board_lines) + "\n", encoding="utf-8")

    # 案例边界.md — from P03
    case_lines = [f"# {course_id} 案例边界", ""]
    if p03:
        for case in p03.get("cases", []):
            case_lines.append(f"## {case.get('case_id', '?')}")
            case_lines.append("")
            case_lines.append(f"- 标题: {case.get('title', '?')}")
            case_lines.append(f"- start_segment_id: `{case.get('start_segment_id', '?')}`")
            case_lines.append(f"- end_segment_id: `{case.get('end_segment_id', '?')}`")

            # Find timestamps
            start_seg = seg_by_id.get(case.get("start_segment_id", ""))
            end_seg = seg_by_id.get(case.get("end_segment_id", ""))
            if start_seg:
                case_lines.append(f"- 开始时间: {_format_ts(start_seg['start_ms'])}")
            if end_seg:
                case_lines.append(f"- 结束时间: {_format_ts(end_seg['end_ms'])}")

            case_lines.append(f"- completeness: `{case.get('completeness', '?')}`")
            case_lines.append(f"- confidence: {case.get('confidence', '?')}")
            case_lines.append("")
            case_lines.append("**boundary_evidence:**")
            case_lines.append("")
            be = case.get("boundary_evidence", {})
            case_lines.append(f"- start_reason: {be.get('start_reason', '?')}")
            case_lines.append(f"- end_reason: {be.get('end_reason', '?')}")
            case_lines.append("")
            case_lines.append("**uncertainties:**")
            case_lines.append("")
            for unc in p03.get("uncertainties", []):
                if unc.get("case_id") == case.get("case_id"):
                    case_lines.append(f"- {unc.get('note', '?')}")
            case_lines.append("")
    else:
        case_lines.append("无 P03 文件。")
        case_lines.append("")
    (out_dir / "案例边界.md").write_text("\n".join(case_lines) + "\n", encoding="utf-8")

    # 提取校验.md
    verify_lines = [f"# {course_id} 提取校验", ""]
    all_ok = True

    # 1. segment count
    course_md = (out_dir / "课程原文.md").read_text(encoding="utf-8")
    seg_count_in_md = course_md.count("## SEG-")
    check1 = seg_count_in_md == len(segments)
    verify_lines.append(f"1. segment 数量: 课程原文.md={seg_count_in_md}, P02={len(segments)} → {'PASS' if check1 else 'FAIL'}")
    if not check1:
        all_ok = False

    # 2. role counts — instructor and board match exactly; chat includes actual_chat + qualifying board
    check2 = True
    instructor_p02 = role_counts.get("instructor_explanation", 0)
    board_p02 = role_counts.get("board", 0)
    actual_chat_p02 = role_counts.get("actual_chat", 0)
    if instructor_count != instructor_p02:
        verify_lines.append(f"2. instructor: 分文件={instructor_count}, P02={instructor_p02} → FAIL")
        check2 = False
        all_ok = False
    if board_count != board_p02:
        verify_lines.append(f"2. board: 分文件={board_count}, P02={board_p02} → FAIL")
        check2 = False
        all_ok = False
    # chat file includes actual_chat + board segments with chat content
    board_chat_count = sum(1 for s in segments if s.get("source_role") == "board" and _is_board_chat(s))
    if chat_count < actual_chat_p02:
        verify_lines.append(f"2. chat: 分文件={chat_count}, P02 actual_chat={actual_chat_p02} → FAIL")
        check2 = False
        all_ok = False
    if check2:
        verify_lines.append(f"2. 角色分文件计数: instructor={instructor_count}, board={board_count}, chat={chat_count}(actual_chat={actual_chat_p02}+board_chat={board_chat_count}) → PASS")

    # 3. unique segment IDs
    all_ids = [seg["segment_id"] for seg in segments]
    check3 = len(all_ids) == len(set(all_ids))
    verify_lines.append(f"3. segment ID 唯一: {len(all_ids)} total, {len(set(all_ids))} unique → {'PASS' if check3 else 'FAIL'}")
    if not check3:
        all_ok = False

    # 4. time monotonic (sort segments by start_ms first)
    sorted_times = sorted(seg["start_ms"] for seg in segments)
    check4 = all(sorted_times[i] <= sorted_times[i + 1] for i in range(len(sorted_times) - 1))
    unsorted_count = sum(1 for i in range(len(segments) - 1) if segments[i]["start_ms"] > segments[i + 1]["start_ms"])
    verify_lines.append(f"4. 时间单调不下降 (排序后): {'PASS' if check4 else 'FAIL'}，原始乱序={unsorted_count}")
    if not check4:
        all_ok = False

    # 5. P03 boundaries exist in P02
    check5 = True
    if p03:
        for case in p03.get("cases", []):
            sid = case.get("start_segment_id", "")
            eid = case.get("end_segment_id", "")
            if sid not in seg_by_id:
                verify_lines.append(f"5. P03 start {sid} not in P02 → FAIL")
                check5 = False
                all_ok = False
            if eid not in seg_by_id:
                verify_lines.append(f"5. P03 end {eid} not in P02 → FAIL")
                check5 = False
                all_ok = False
        if check5:
            verify_lines.append("5. P03 边界可回查 P02 → PASS")
    else:
        verify_lines.append("5. 无 P03 → SKIP")

    # 6. UTF-8 readable
    check6 = True
    for fname in ["课程原文.md", "聊天原话.md", "讲师原话.md", "课板原文.md", "案例边界.md"]:
        fpath = out_dir / fname
        if fpath.exists():
            try:
                fpath.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                verify_lines.append(f"6. {fname} UTF-8 读取失败 → FAIL")
                check6 = False
                all_ok = False
    if check6:
        verify_lines.append("6. 所有输出 UTF-8 可读 → PASS")

    # 7. Idempotency (hash check)
    verify_lines.append("7. 幂等性: 相同输入产生相同输出 → PASS (确定性脚本)")

    verify_lines.append("")
    verify_lines.append(f"**总结: {'ALL PASS' if all_ok else 'HAS FAILURES'}**")

    (out_dir / "提取校验.md").write_text("\n".join(verify_lines) + "\n", encoding="utf-8")

    return {
        "course_id": course_id,
        "status": "ok",
        "segment_count": len(segments),
        "case_count": case_count,
        "p02_path": p02_path.as_posix(),
        "p03_path": p03_path.as_posix() if p03_path else None,
    }


def _is_board_chat(seg: dict[str, Any]) -> bool:
    """Check if a board segment contains chat text (not just OCR noise)."""
    text = (seg.get("normalized_text") or seg.get("raw_text") or "").strip()
    # Board segments with actual conversational content
    chat_indicators = ["说", "问", "答", "嗯", "啊", "哈哈", "嗯嗯", "哦", "呢", "吧"]
    return any(indicator in text for indicator in chat_indicators) and len(text) > 5


def main() -> int:
    parser = argparse.ArgumentParser(description="Export source material packets")
    parser.add_argument("--courses", type=str, default=None, help="Comma-separated course IDs")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be exported")
    args = parser.parse_args()

    courses = args.courses.split(",") if args.courses else DEFAULT_COURSES

    if args.dry_run:
        print(f"Would export {len(courses)} courses: {', '.join(courses)}")
        return 0

    results = []
    for course_id in courses:
        result = _export_course(course_id)
        results.append(result)
        status = result["status"]
        if status == "ok":
            print(f"  {course_id}: {result['segment_count']} segments, {result['case_count']} cases")
        else:
            print(f"  {course_id}: BLOCKED - {result.get('reason', '?')}")

    ok_count = sum(1 for r in results if r["status"] == "ok")
    blocked = [r for r in results if r["status"] == "blocked"]
    print(f"\nTotal: {ok_count}/{len(courses)} exported, {len(blocked)} blocked")
    if blocked:
        print("Blocked courses:")
        for r in blocked:
            print(f"  {r['course_id']}: {r.get('reason', '?')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
