"""Neutron pantry/fridge/freezer scanner (nutrition module).

Mirrors recognition.py exactly: images -> Bedrock Converse with a FORCED tool
call -> validated draft item list. The draft is never trusted or persisted —
the client shows it for edit/removal and only a user-confirmed list is saved
via PUT /nutrition/pantry. Photos are processed and discarded (never stored),
which is the module's privacy promise.

Provider selection reuses settings.vision_provider (stub | bedrock), so local
dev works with no AWS credentials.
"""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

VALID_CATEGORIES = ("pantry", "fridge", "freezer", "other")
VALID_DENSITIES = ("high", "medium", "low")


class ScannedFoodItem(BaseModel):
    """One draft food item from a scan, with protein info and confidence."""

    name: str
    quantity: str = ""                    # freeform estimate: "2 cans", "~500 g", "1 dozen"
    category: str = "pantry"              # pantry | fridge | freezer | other
    protein_per_100g: float | None = None
    protein_density: str = "low"          # high (>=15g/100g) | medium (5-15) | low (<5)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PantryScanResult(BaseModel):
    """Full draft food list plus which scanner produced it (provenance)."""

    items: list[ScannedFoodItem]
    recognizer: str


# Forced tool: structured output, no free-text parsing (same pattern as
# SUBMIT_INVENTORY_TOOL in recognition.py).
SUBMIT_PANTRY_TOOL = {
    "toolSpec": {
        "name": "submit_pantry",
        "description": "Report every distinct food or ingredient visible in the photos.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "string"},
                                "category": {"type": "string", "enum": list(VALID_CATEGORIES)},
                                "protein_per_100g": {"type": ["number", "null"]},
                                "protein_density": {"type": "string", "enum": list(VALID_DENSITIES)},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": ["name", "confidence"],
                        },
                    }
                },
                "required": ["items"],
            }
        },
    }
}

PANTRY_SCAN_PROMPT = (
    "You are cataloguing food from photos of a home pantry, fridge, or freezer "
    "for a nutrition app whose users must hit a daily protein target. Identify "
    "every distinct food or ingredient you can actually see. For each item: "
    "give a short generic name (e.g. 'canned black beans', 'chicken breast', "
    "'Greek yogurt' — brand names only when clearly readable and useful), a "
    "rough quantity estimate ('2 cans', '~500 g', 'half carton'), which storage "
    "location the photo shows, an approximate protein_per_100g if you know the "
    "food (null if unsure), and a protein_density bucket: high (>=15 g/100g), "
    "medium (5-15), low (<5). Set LOW confidence for anything partially hidden, "
    "blurry, or ambiguous — do not guess items you cannot see. Ignore non-food "
    "objects, cleaning products, and pet food. Call submit_pantry with your "
    "findings."
)


def parse_pantry_tool_output(response: dict, recognizer_name: str) -> PantryScanResult:
    """Pure parser (unit-testable, no network). Coerces the forced tool-use
    input into a validated PantryScanResult; bad enums fall back to safe values."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_input = None
    for block in content:
        if "toolUse" in block and block["toolUse"].get("name") == "submit_pantry":
            tool_input = block["toolUse"].get("input", {})
            break
    if tool_input is None:
        return PantryScanResult(items=[], recognizer=recognizer_name)

    items: list[ScannedFoodItem] = []
    for raw in tool_input.get("items", []):
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        category = raw.get("category", "pantry")
        if category not in VALID_CATEGORIES:
            category = "other"
        density = raw.get("protein_density", "low")
        if density not in VALID_DENSITIES:
            density = "low"
        try:
            conf = min(1.0, max(0.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        ppg = raw.get("protein_per_100g")
        try:
            ppg = None if ppg is None else max(0.0, float(ppg))
        except (TypeError, ValueError):
            ppg = None
        items.append(ScannedFoodItem(
            name=name[:120],
            quantity=str(raw.get("quantity", "") or "")[:60],
            category=category,
            protein_per_100g=ppg,
            protein_density=density,
            confidence=conf,
        ))
    return PantryScanResult(items=items, recognizer=recognizer_name)


class DevStubPantryScanner:
    """Deterministic stub so the scan/confirm flow is testable without AWS."""

    name = "stub"

    async def scan(self, image_bytes: list[bytes]) -> PantryScanResult:
        items = [
            ScannedFoodItem(name="chicken breast", quantity="~700 g", category="fridge",
                            protein_per_100g=31, protein_density="high", confidence=0.9),
            ScannedFoodItem(name="Greek yogurt (plain)", quantity="1 tub", category="fridge",
                            protein_per_100g=10, protein_density="medium", confidence=0.85),
            ScannedFoodItem(name="canned black beans", quantity="3 cans", category="pantry",
                            protein_per_100g=9, protein_density="medium", confidence=0.8),
            ScannedFoodItem(name="rolled oats", quantity="1 bag", category="pantry",
                            protein_per_100g=13, protein_density="medium", confidence=0.75),
            ScannedFoodItem(name="frozen shrimp", quantity="1 bag", category="freezer",
                            protein_per_100g=24, protein_density="high", confidence=0.7),
            ScannedFoodItem(name="eggs", quantity="1 dozen", category="fridge",
                            protein_per_100g=13, protein_density="medium", confidence=0.9),
            ScannedFoodItem(name="spinach", quantity="1 bag", category="fridge",
                            protein_per_100g=3, protein_density="low", confidence=0.6),
        ]
        return PantryScanResult(items=items, recognizer=self.name)


class BedrockClaudePantryScanner:
    """Production scanner: Claude multimodal via Bedrock Converse (forced tool)."""

    def __init__(self, settings):
        import boto3  # lazy: stub path needs no AWS deps
        self._model_id = settings.bedrock_model_id
        # A full pantry/fridge scan is 20-40 items x several fields — far bigger
        # than an equipment inventory. Below ~4096 the forced tool call gets
        # truncated mid-JSON and parses to ZERO items (looks like "found nothing").
        self._max_tokens = max(settings.bedrock_max_tokens, 4096)
        self.name = f"bedrock:{settings.bedrock_model_id}"
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def _detect_format(self, data: bytes) -> str:
        """Sniff jpeg/png/webp from magic bytes."""
        if data[:3] == b"\xff\xd8\xff":
            return "jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "png"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp"
        return "jpeg"

    def _invoke(self, image_bytes: list[bytes]) -> dict:
        """Synchronous Bedrock Converse call (run in a thread by scan)."""
        content: list[dict] = [{"text": PANTRY_SCAN_PROMPT}]
        for data in image_bytes:
            content.append({
                "image": {"format": self._detect_format(data), "source": {"bytes": data}}
            })
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": 0.0},
            toolConfig={
                "tools": [SUBMIT_PANTRY_TOOL],
                "toolChoice": {"tool": {"name": "submit_pantry"}},
            },
        )

    async def scan(self, image_bytes: list[bytes]) -> PantryScanResult:
        imgs = image_bytes[:4]  # same Bedrock payload cap as equipment recognition
        response = await asyncio.to_thread(self._invoke, imgs)
        result = parse_pantry_tool_output(response, self.name)
        if not result.items:
            # Empty parse is almost always truncation or an oversized payload,
            # not an actually-empty kitchen — leave a trail for `aws logs tail`.
            _log.warning(
                "pantry scan parsed 0 items: stopReason=%s images=%d bytes=%d",
                response.get("stopReason"), len(imgs), sum(len(b) for b in imgs),
            )
        return result


_scanner = None


def build_pantry_scanner(settings):
    """Build (once) and return the scanner selected by settings.vision_provider."""
    global _scanner
    if _scanner is None:
        if settings.vision_provider == "bedrock":
            _scanner = BedrockClaudePantryScanner(settings)
        else:
            _scanner = DevStubPantryScanner()
    return _scanner
