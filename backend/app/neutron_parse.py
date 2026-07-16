"""Neutron voice-log AI fallback: food phrase -> protein estimate.

The mobile app parses dictated meals ON DEVICE (bundled food DB + fuzzy
matcher + local alias cache). Only phrases the device cannot resolve reach
this module — and even then the router checks `nutrition_parse_cache` first,
so any given normalized phrase hits Bedrock at most ONCE across ALL users.

Mirrors neutron_vision.py / neutron_recipes.py exactly: forced tool call on
Bedrock Converse (temperature 0, maxTokens floor 4096), pure unit-testable
parser, and a deterministic stub engine selected by settings.vision_provider
(stub | bedrock) so local dev needs no AWS credentials.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)


def normalize_phrase(raw: str) -> str:
    """Canonical cache key: lowercase, ascii-fold, strip punctuation,
    collapse whitespace. MUST stay in sync with the mobile matcher's
    normalize() so device cache and server cache agree on keys."""
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9%./ ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()[:200]


class ParsedFood(BaseModel):
    """Protein estimate for one dictated food phrase."""

    phrase: str                             # the input phrase, echoed back
    name: str                                # canonical short food name
    protein_per_100g: float = Field(ge=0, le=100)
    portion_est_g: float = Field(gt=0, le=3000)   # grams for the DESCRIBED portion
    protein_g: float = Field(ge=0, le=400)        # protein in that portion
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ParseResult(BaseModel):
    """Batch parse output plus which parser produced it (stub/bedrock/cache)."""

    items: list[ParsedFood]
    parser: str


SUBMIT_FOODS_TOOL = {
    "toolSpec": {
        "name": "submit_food_items",
        "description": "Report a protein estimate for each described food/portion.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "phrase": {"type": "string"},
                                "name": {"type": "string"},
                                "protein_per_100g": {"type": "number"},
                                "portion_est_g": {"type": "number"},
                                "protein_g": {"type": "number"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": ["phrase", "name", "protein_g"],
                        },
                    }
                },
                "required": ["items"],
            }
        },
    }
}


def build_parse_prompt(phrases: list[str]) -> str:
    """One batched prompt covering every missed phrase (single model call)."""
    numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(phrases))
    return (
        "You estimate protein for a nutrition tracker whose users must hit a "
        "daily protein target. Each line below is a food (possibly with a "
        "portion) that a user dictated. For EVERY line, echo the phrase back "
        "exactly, give a short canonical name, typical protein_per_100g (as "
        "eaten/cooked), a realistic portion_est_g for the described or, if "
        "unstated, a typical single serving, and protein_g for that portion "
        "(protein_per_100g * portion_est_g / 100, rounded to 1 decimal). "
        "Estimates should be practical, not lab-precise. Lower confidence for "
        "vague or composite dishes. If a line is not food, return it with "
        "protein_g 0 and confidence 0. Call submit_food_items with one entry "
        "per line, same order.\n\n" + numbered
    )


def parse_foods_tool_output(response: dict, parser_name: str,
                            phrases: list[str]) -> ParseResult:
    """Pure parser (unit-testable, no network). Coerces the forced tool-use
    input into validated ParsedFood rows; recomputes/clamps inconsistent
    numbers instead of trusting the model's arithmetic."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_input = None
    for block in content:
        if "toolUse" in block and block["toolUse"].get("name") == "submit_food_items":
            tool_input = block["toolUse"].get("input", {})
            break
    if tool_input is None:
        return ParseResult(items=[], parser=parser_name)

    items: list[ParsedFood] = []
    raws = tool_input.get("items", [])
    for i, raw in enumerate(raws):
        name = str(raw.get("name", "")).strip()
        if not name:
            continue

        def _num(key: str, lo: float, hi: float, default: float) -> float:
            try:
                return min(hi, max(lo, float(raw.get(key))))
            except (TypeError, ValueError):
                return default

        ppg = _num("protein_per_100g", 0.0, 100.0, 0.0)
        portion = _num("portion_est_g", 1.0, 3000.0, 100.0)
        protein = _num("protein_g", 0.0, 400.0, -1.0)
        derived = round(ppg * portion / 100.0, 1)
        # Trust the derived number when the model's total is missing or wildly
        # off (>25% drift) — arithmetic is ours, food knowledge is the model's.
        if protein < 0 or (derived > 0 and abs(protein - derived) > 0.25 * derived):
            protein = derived
        phrase = str(raw.get("phrase", "")).strip() or (
            phrases[i] if i < len(phrases) else name)
        items.append(ParsedFood(
            phrase=phrase[:200], name=name[:120], protein_per_100g=ppg,
            portion_est_g=portion, protein_g=min(400.0, protein),
            confidence=_num("confidence", 0.0, 1.0, 0.5),
        ))
    return ParseResult(items=items, parser=parser_name)


class DevStubFoodParser:
    """Deterministic keyword heuristic so the voice-log flow (device miss ->
    /nutrition/parse -> cache) is fully testable without AWS."""

    name = "stub"

    _RULES = (  # (keyword, protein_per_100g, portion_g)
        ("chicken", 31.0, 150.0), ("beef", 26.0, 150.0), ("salmon", 25.0, 150.0),
        ("egg", 13.0, 100.0), ("yogurt", 10.0, 170.0), ("shake", 8.0, 350.0),
        ("cheese", 22.0, 30.0), ("beans", 9.0, 130.0), ("rice", 2.7, 150.0),
        ("bread", 9.0, 50.0),
    )

    async def parse(self, phrases: list[str]) -> ParseResult:
        items = []
        for p in phrases:
            low = p.lower()
            ppg, portion = 5.0, 100.0
            for kw, k_ppg, k_portion in self._RULES:
                if kw in low:
                    ppg, portion = k_ppg, k_portion
                    break
            items.append(ParsedFood(
                phrase=p[:200], name=normalize_phrase(p)[:120] or "food",
                protein_per_100g=ppg, portion_est_g=portion,
                protein_g=round(ppg * portion / 100.0, 1), confidence=0.4,
            ))
        return ParseResult(items=items, parser=self.name)


class BedrockClaudeFoodParser:
    """Production parser: text-only Bedrock Converse with a forced tool call."""

    def __init__(self, settings):
        import boto3  # lazy: stub path needs no AWS deps
        self._model_id = settings.bedrock_model_id
        # Same floor as pantry/recipes: below ~4096 the forced tool call can
        # truncate mid-JSON and parse to zero items.
        self._max_tokens = max(settings.bedrock_max_tokens, 4096)
        self.name = f"bedrock:{settings.bedrock_model_id}"
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def _invoke(self, prompt: str) -> dict:
        """Synchronous Bedrock Converse call (run in a thread by parse)."""
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": 0.0},
            toolConfig={
                "tools": [SUBMIT_FOODS_TOOL],
                "toolChoice": {"tool": {"name": "submit_food_items"}},
            },
        )

    async def parse(self, phrases: list[str]) -> ParseResult:
        response = await asyncio.to_thread(self._invoke, build_parse_prompt(phrases))
        result = parse_foods_tool_output(response, self.name, phrases)
        if not result.items:
            _log.warning("food parse returned 0 items: stopReason=%s phrases=%d",
                         response.get("stopReason"), len(phrases))
        return result


def build_food_parser(settings):
    """Factory: Bedrock parser or dev stub, per settings.vision_provider."""
    if settings.vision_provider == "bedrock":
        return BedrockClaudeFoodParser(settings)
    return DevStubFoodParser()
