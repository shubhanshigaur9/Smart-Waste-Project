"""Rule-based waste guidance, kept separate from visual item recognition."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).with_name("waste_rules.json")


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _contains_any(text: str, terms: list[str]) -> bool:
    normalized = f" {_normalize(text)} "
    return any(f" {_normalize(term)} " in normalized for term in terms)


def _read_rules() -> dict[str, Any]:
    with RULES_PATH.open("r", encoding="utf-8") as rules_file:
        return json.load(rules_file)


def recommend_disposal(
    *,
    item: str,
    material: str,
    condition: str,
    context: str | None = None,
    confidence: str = "medium",
) -> dict[str, str | bool]:
    """Return an actionable, explainable decision for an identified item."""

    data = _read_rules()
    for rule in data["rules"]:
        item_terms = rule.get("items", [])
        material_terms = rule.get("materials", [])
        condition_terms = rule.get("conditions", [])
        if item_terms and not _contains_any(item, item_terms) and not _contains_any(material, material_terms):
            continue
        if not item_terms and material_terms and not _contains_any(material, material_terms):
            continue
        if condition_terms and not _contains_any(condition, condition_terms):
            continue
        return _format_result(rule, item, material, condition, context, confidence)

    fallback = data["fallback"]
    return _format_result(fallback, item, material, condition, context, confidence)


def _format_result(
    rule: dict[str, Any],
    item: str,
    material: str,
    condition: str,
    context: str | None,
    confidence: str,
) -> dict[str, str | bool]:
    reason = rule["reason"]
    if confidence == "low":
        reason = f"The image match is uncertain, so treat this as a starting point. {reason}"
    if context and _normalize(context) not in {"not sure", "unsure", "i m not sure"}:
        reason = f"For {context.lower()}, {reason[0].lower()}{reason[1:]}"
        context_notes = _read_rules().get("context_guidance", {})
        note = context_notes.get(_normalize(context))
        if note:
            reason = f"{reason} {note}"
    if rule.get("local_check"):
        reason = f"{reason} Collection rules differ between municipalities, so confirm the accepted items with your local waste service."
    return {
        "item": item,
        "material": material,
        "condition": condition,
        "context": context or "Not provided",
        "recommendation": rule["recommendation"],
        "reason": reason,
        "preparation": rule.get("preparation", "Check your local waste service for the safest next step."),
        "confidence": confidence,
        "needs_review": confidence == "low",
    }
