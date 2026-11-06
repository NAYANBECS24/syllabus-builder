"""Deterministic, source-grounded book research agent.

The agent orchestrates local page search and syllabus alignment.  It does not
invent summaries: every reading step points to a source page and excerpt.
Online catalog enrichment is attached by the HTTP layer using metadata only.
"""
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Tuple
import re
import unicodedata


MAX_ALIGNMENT_TOPICS = 40
MAX_READING_STEPS = 8


def _text(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value).casefold())
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def _topic_rows(context: Any) -> Tuple[Dict[str, str], List[Dict[str, Any]], int]:
    """Return course identity and unique source topics from a Task 2 object."""
    if not isinstance(context, dict):
        return {}, [], 0
    task2 = context.get("task2") if isinstance(context.get("task2"), dict) else context
    course_raw = task2.get("course") if isinstance(task2.get("course"), dict) else {}
    course = {
        "code": _text(course_raw.get("code"), 40),
        "title": _text(course_raw.get("title"), 180),
    }
    unique = OrderedDict()
    total = 0
    units = task2.get("units") if isinstance(task2.get("units"), list) else []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        try:
            number = int(unit.get("number"))
        except (TypeError, ValueError):
            number = len(unique) + 1
        unit_title = _text(unit.get("title"), 180)
        topics = unit.get("topics") if isinstance(unit.get("topics"), list) else []
        if topics:
            candidates = [topic.get("text") for topic in topics if isinstance(topic, dict)]
        else:
            candidates = [unit.get("text")]
        for candidate in candidates:
            topic = _text(candidate, 240)
            if len(topic) < 2:
                continue
            total += 1
            key = _key(topic)
            if not key or key in unique:
                continue
            unique[key] = {
                "text": topic,
                "unit": number,
                "unit_title": unit_title,
            }
    return course, list(unique.values())[:MAX_ALIGNMENT_TOPICS], total


def _reading_path(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    steps = []
    seen_pages = set()
    for result in results:
        try:
            page = int(result.get("page"))
        except (TypeError, ValueError):
            continue
        if page < 1 or page in seen_pages:
            continue
        seen_pages.add(page)
        position = len(steps)
        if position == 0:
            role = "Start here"
            reason = "Strongest source match for the requested topic"
        elif result.get("exact_match"):
            role = "Confirm"
            reason = "Another page contains the exact phrase"
        elif _number(result.get("term_coverage")) >= 80:
            role = "Deepen"
            reason = "Covers most of the requested concepts"
        else:
            role = "Extend"
            reason = "Adds related context from the book"
        steps.append({
            "order": position + 1,
            "page": page,
            "role": role,
            "reason": reason,
            "section": _text(result.get("section"), 220),
            "relevance": int(_number(result.get("relevance"))),
            "evidence": _text(result.get("snippet"), 500),
        })
        if len(steps) >= MAX_READING_STEPS:
            break
    return steps


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_report(
    pages: List[Dict[str, Any]],
    outline: List[Dict[str, Any]],
    query: str,
    mode: str,
    primary_results: List[Dict[str, Any]],
    search: Callable[[List[Dict[str, Any]], str, Optional[List[Dict[str, Any]]], str], Tuple[List[Dict[str, Any]], int]],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a local agent report using only page evidence and syllabus data."""
    course, topics, source_topic_total = _topic_rows(context or {})
    covered, gaps = [], []
    topic_pages = {}
    for topic in topics:
        matches, total = search(pages, topic["text"], outline, "balanced")
        best = matches[0] if matches else None
        row = {
            "text": topic["text"],
            "unit": topic["unit"],
            "unit_title": topic["unit_title"],
        }
        if best and _number(best.get("relevance")) >= 35:
            row.update({
                "page": int(best["page"]),
                "relevance": int(_number(best.get("relevance"))),
                "evidence": _text(best.get("snippet"), 360),
                "matching_pages": int(total),
            })
            covered.append(row)
            topic_pages.setdefault(int(best["page"]), best)
        else:
            gaps.append(row)

    combined_results = list(primary_results)
    existing_pages = {int(item.get("page", 0)) for item in combined_results}
    for page, result in topic_pages.items():
        if page not in existing_pages:
            combined_results.append(result)
    combined_results.sort(key=lambda item: (-_number(item.get("score")), int(item.get("page", 0))))

    checked = len(topics)
    coverage = round((len(covered) / checked) * 100) if checked else None
    if primary_results:
        status = "ready"
        message = "A source-backed reading path is ready."
    elif checked and covered:
        status = "context_matches"
        message = "The exact request was not found, but syllabus-aligned pages were located."
    else:
        status = "review_required"
        message = "No reliable page evidence was found for this request."

    next_queries = []
    for item in gaps[:5]:
        if item["text"] not in next_queries:
            next_queries.append(item["text"])
    if not primary_results:
        short_terms = [word for word in _key(query).split() if len(word) >= 4]
        next_queries = short_terms[:3] + [item for item in next_queries if item not in short_terms]

    return {
        "version": "1.0",
        "engine": "local-evidence-agent",
        "status": status,
        "message": message,
        "mission": _text(query, 160),
        "course": course,
        "reading_path": _reading_path(combined_results),
        "syllabus_alignment": {
            "available": bool(checked),
            "source_topic_count": source_topic_total,
            "topics_checked": checked,
            "topics_covered": len(covered),
            "coverage_percent": coverage,
            "covered": covered[:20],
            "gaps": gaps[:20],
            "limited": source_topic_total > MAX_ALIGNMENT_TOPICS,
        },
        "next_queries": next_queries[:8],
        "evidence_policy": "Every reading step and covered topic points to text found on the uploaded book page.",
        "online": {
            "requested": False,
            "status": "not_requested",
            "message": "Local book analysis completed without an internet request.",
            "metadata_only": True,
            "results": [],
        },
    }
