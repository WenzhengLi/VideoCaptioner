#!/usr/bin/env python3
"""Compare P03 knowledge-v002 vs knowledge-v003 case boundary outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AD_HINTS = ("广告", "加微信", "优惠", "报名", "链接", "私聊我领")
CHATTER_HINTS = ("开场", "调试", "麦克风", "听得到", "稍微等一下", "今天先到这")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _metrics(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("segmentation_metrics")
    if isinstance(metrics, dict) and metrics.get("input_segment_count"):
        input_count = int(metrics["input_segment_count"])
        assigned = int(metrics.get("assigned_segment_count") or 0)
        unassigned = int(metrics.get("unassigned_segment_count") or 0)
        case_count = int(metrics.get("case_count") or len(payload.get("cases") or []))
    else:
        cases = payload.get("cases") or []
        unassigned_ids = payload.get("unassigned_segment_ids") or []
        assigned = 0
        for case in cases:
            if not isinstance(case, dict):
                continue
            seg_ids = case.get("segment_ids")
            if isinstance(seg_ids, list):
                assigned += len(seg_ids)
        unassigned = len(unassigned_ids)
        input_count = assigned + unassigned
        case_count = len(cases)
    ratio = round(unassigned / input_count, 4) if input_count else None
    return {
        "case_count": case_count,
        "assigned_segment_count": assigned,
        "unassigned_segment_count": unassigned,
        "input_segment_count": input_count,
        "unassigned_ratio": ratio,
    }


def _case_ranges(payload: dict[str, Any], index_by_id: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in payload.get("cases") or []:
        if not isinstance(case, dict):
            continue
        start = str(case.get("start_segment_id") or "")
        end = str(case.get("end_segment_id") or "")
        if start not in index_by_id or end not in index_by_id:
            continue
        start_i = index_by_id[start]
        end_i = index_by_id[end]
        evidence = case.get("boundary_evidence") or {}
        evidence_ids = []
        if isinstance(evidence, dict):
            evidence_ids = [
                str(x) for x in (evidence.get("evidence_segment_ids") or []) if x
            ]
        outside = [
            sid
            for sid in evidence_ids
            if sid not in index_by_id or not (start_i <= index_by_id[sid] <= end_i)
        ]
        rows.append(
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "start_segment_id": start,
                "end_segment_id": end,
                "start_index": start_i,
                "end_index": end_i,
                "size": end_i - start_i + 1,
                "completeness": case.get("completeness"),
                "boundary_evidence_outside_range": outside,
            }
        )
    return rows


def _segment_text_map(p02: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for seg in p02.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "")
        text = str(
            seg.get("normalized_text")
            or seg.get("text")
            or seg.get("raw_text")
            or ""
        )
        result[sid] = text
    return result


def _looks_like_ad_or_chatter(text: str) -> bool:
    lowered = text.lower()
    return any(h in text or h.lower() in lowered for h in AD_HINTS + CHATTER_HINTS)


def compare_course(
    course_id: str,
    p02_path: Path,
    v002_path: Path,
    v003_path: Path,
    v002_qa_path: Path | None = None,
    v003_qa_path: Path | None = None,
) -> dict[str, Any]:
    p02 = _load(p02_path)
    v002 = _load(v002_path)
    v003 = _load(v003_path)
    source_ids = [
        str(item.get("segment_id"))
        for item in (p02.get("segments") or [])
        if isinstance(item, dict) and item.get("segment_id")
    ]
    index_by_id = {sid: i for i, sid in enumerate(source_ids)}
    text_map = _segment_text_map(p02)

    m002 = _metrics(v002)
    m003 = _metrics(v003)
    ranges002 = _case_ranges(v002, index_by_id)
    ranges003 = _case_ranges(v003, index_by_id)

    unassigned002 = set(str(x) for x in (v002.get("unassigned_segment_ids") or []))
    unassigned003 = set(str(x) for x in (v003.get("unassigned_segment_ids") or []))
    newly_assigned = sorted(unassigned002 - unassigned003)
    newly_unassigned = sorted(unassigned003 - unassigned002)

    suspicious_forced_into_cases: list[dict[str, Any]] = []
    for sid in newly_assigned[:200]:
        text = text_map.get(sid, "")
        if _looks_like_ad_or_chatter(text):
            suspicious_forced_into_cases.append(
                {"segment_id": sid, "text_preview": text[:120]}
            )

    # Detect possible fragmentation: same rough title region split into more cases
    fragmentation_risk = (
        m003["case_count"] > m002["case_count"] + 1
        and (m003["unassigned_ratio"] or 0) <= (m002["unassigned_ratio"] or 0)
    )

    evidence_outside = [
        {"case_id": row["case_id"], "outside": row["boundary_evidence_outside_range"]}
        for row in ranges003
        if row["boundary_evidence_outside_range"]
    ]

    v002_qa = None
    v003_qa = None
    if v002_qa_path and v002_qa_path.exists():
        v002_qa = _load(v002_qa_path)
    if v003_qa_path and v003_qa_path.exists():
        v003_qa = _load(v003_qa_path)

    coverage_ok = bool(
        isinstance(v003_qa, dict)
        and (v003_qa.get("checks") or {}).get("complete_segment_coverage")
        and (v003_qa.get("checks") or {}).get("cases_do_not_overlap")
    ) or (
        # fallback without QA file
        abs(
            m003["assigned_segment_count"]
            + m003["unassigned_segment_count"]
            - m003["input_segment_count"]
        )
        == 0
    )

    delta_unassigned = None
    if m002["unassigned_ratio"] is not None and m003["unassigned_ratio"] is not None:
        delta_unassigned = round(m003["unassigned_ratio"] - m002["unassigned_ratio"], 4)

    return {
        "course_id": course_id,
        "v002": m002,
        "v003": m003,
        "delta": {
            "case_count": m003["case_count"] - m002["case_count"],
            "unassigned_segment_count": m003["unassigned_segment_count"]
            - m002["unassigned_segment_count"],
            "unassigned_ratio": delta_unassigned,
        },
        "qa": {
            "v002": (v002_qa or {}).get("status") if isinstance(v002_qa, dict) else "missing",
            "v003": (v003_qa or {}).get("status") if isinstance(v003_qa, dict) else "missing",
        },
        "coverage_ok": coverage_ok,
        "newly_assigned_count": len(newly_assigned),
        "newly_unassigned_count": len(newly_unassigned),
        "suspicious_forced_ad_or_chatter": suspicious_forced_into_cases[:20],
        "fragmentation_risk": fragmentation_risk,
        "v003_boundary_evidence_outside_range": evidence_outside,
        "v002_cases": [
            {
                "case_id": r["case_id"],
                "title": r["title"],
                "size": r["size"],
                "completeness": r["completeness"],
            }
            for r in ranges002
        ],
        "v003_cases": [
            {
                "case_id": r["case_id"],
                "title": r["title"],
                "size": r["size"],
                "completeness": r["completeness"],
            }
            for r in ranges003
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# P03 v002 vs v003 固定回归",
        "",
        f"- courses: {', '.join(c['course_id'] for c in report['courses'])}",
        f"- adoption_recommendation: `{report['adoption_recommendation']}`",
        "",
        "| Course | v002 cases | v003 cases | v002 unass% | v003 unass% | Δ unass% | coverage | QA v003 | risks |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for course in report["courses"]:
        risks: list[str] = []
        if course["suspicious_forced_ad_or_chatter"]:
            risks.append("forced_ad_or_chatter")
        if course["fragmentation_risk"]:
            risks.append("fragmentation")
        if course["v003_boundary_evidence_outside_range"]:
            risks.append("evidence_outside")
        if not course["coverage_ok"]:
            risks.append("coverage_fail")
        unk2 = course["v002"]["unassigned_ratio"]
        unk3 = course["v003"]["unassigned_ratio"]
        delta = course["delta"]["unassigned_ratio"]
        lines.append(
            f"| {course['course_id']} | {course['v002']['case_count']} | "
            f"{course['v003']['case_count']} | "
            f"{'n/a' if unk2 is None else f'{unk2*100:.1f}'} | "
            f"{'n/a' if unk3 is None else f'{unk3*100:.1f}'} | "
            f"{'n/a' if delta is None else f'{delta*100:+.1f}'} | "
            f"{'ok' if course['coverage_ok'] else 'FAIL'} | "
            f"{course['qa']['v003']} | {','.join(risks) or '-'} |"
        )
    lines.extend(["", "## 逐课说明", ""])
    for course in report["courses"]:
        lines.append(f"### {course['course_id']}")
        lines.append("")
        lines.append(
            f"- newly_assigned={course['newly_assigned_count']}, "
            f"newly_unassigned={course['newly_unassigned_count']}"
        )
        if course["suspicious_forced_ad_or_chatter"]:
            lines.append(
                f"- suspicious forced segments: "
                f"{len(course['suspicious_forced_ad_or_chatter'])} (see JSON)"
            )
        lines.append(
            "- v003 cases: "
            + "; ".join(
                f"{c['case_id']}({c['size']},{c['completeness']})"
                for c in course["v003_cases"]
            )
        )
        lines.append("")
    lines.append("## 采用规则结论")
    lines.append("")
    lines.append(report["adoption_notes"])
    lines.append("")
    return "\n".join(lines)


def decide_adoption(courses: list[dict[str, Any]]) -> tuple[str, str]:
    blockers: list[str] = []
    warnings: list[str] = []
    improved: list[str] = []
    for course in courses:
        cid = course["course_id"]
        if not course["coverage_ok"] or course["qa"]["v003"] != "pass":
            blockers.append(f"{cid}: coverage/QA")
        if course["suspicious_forced_ad_or_chatter"]:
            # Soft warning: heuristic may match closing WeChat/signup chatter.
            count = len(course["suspicious_forced_ad_or_chatter"])
            if count >= 5:
                blockers.append(f"{cid}: many forced ad/chatter segments ({count})")
            else:
                warnings.append(f"{cid}: soft ad/chatter heuristic hits={count}")
        if course["v003_boundary_evidence_outside_range"]:
            warnings.append(f"{cid}: boundary evidence cites outside-range segments")
        if course["fragmentation_risk"]:
            blockers.append(f"{cid}: fragmentation risk")
        delta = course["delta"]["unassigned_ratio"]
        if cid in {"C003", "C008"} and delta is not None and delta < -0.05:
            improved.append(cid)
        if cid in {"C006", "C010"} and delta is not None and delta > 0.05:
            blockers.append(f"{cid}: baseline regression >5pp unassigned")
    notes_extra = ("；警告：" + "; ".join(warnings)) if warnings else ""
    if blockers:
        return (
            "keep_v002_pending_prompt_fix",
            "存在阻断项，暂不把 v003 作为证据基线："
            + "; ".join(blockers)
            + notes_extra,
        )
    if improved:
        return (
            "adopt_v003_hybrid",
            "固定高未分配课有改善且无基线硬退化；建议 hybrid："
            "改善课用 v003，其余可暂留 v002；新课默认 v003。"
            + "改善课="
            + ", ".join(improved)
            + notes_extra,
        )
    return (
        "keep_v002_no_clear_gain",
        "覆盖与风险可接受，但高未分配课未形成明确改善，暂保持 v002。"
        + notes_extra,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--courses",
        default="C003,C008,C006,C010",
        help="comma-separated course ids",
    )
    parser.add_argument("--v002", default="knowledge-v002")
    parser.add_argument("--v003", default="knowledge-v003")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evaluation/p03-v002-v003-regression.md"),
    )
    args = parser.parse_args()

    courses: list[dict[str, Any]] = []
    for course_id in [c.strip() for c in args.courses.split(",") if c.strip()]:
        course_dir = args.data_root / "courses" / course_id
        courses.append(
            compare_course(
                course_id,
                course_dir / "02_normalized" / f"P02-{args.v002}.json",
                course_dir / "03_cases" / f"P03-{args.v002}.json",
                course_dir / "03_cases" / f"P03-{args.v003}.json",
                course_dir / "qa" / f"P03-{args.v002}-qa.json",
                course_dir / "qa" / f"P03-{args.v003}-qa.json",
            )
        )
    recommendation, notes = decide_adoption(courses)
    report = {
        "schema_version": "1.0",
        "courses": courses,
        "adoption_recommendation": recommendation,
        "adoption_notes": notes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output.with_suffix(".json")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {args.output} and {json_path}")
    print(f"adoption={recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
