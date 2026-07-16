"""Equipment recognition (spec R1).

The recognizer takes one or more images and returns a DRAFT inventory as
structured JSON validated against the taxonomy. The draft is never trusted —
the user confirms/corrects it (spec R1, R3) before it becomes canonical.

This module defines the provider-agnostic interface and a dev stub. The concrete
vision-LLM adapter is added once the provider is locked; swapping providers is a
single new subclass, exactly like email_sender.
"""
from __future__ import annotations

import abc
import asyncio


from pydantic import BaseModel, Field

from .equipment import EquipmentType, is_valid_type


class RecognizedItem(BaseModel):
    """One draft inventory item as reported by the recognizer, with its confidence."""

    type: EquipmentType
    quantity: int = Field(default=1, ge=1)
    load_min: float | None = None
    load_max: float | None = None
    load_increment: float | None = None
    attributes: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)


class RecognitionResult(BaseModel):
    """A full draft inventory plus which recognizer produced it (provenance)."""

    items: list[RecognizedItem]
    recognizer: str  # name/version of the recognizer that produced this


# JSON schema we instruct the vision LLM to emit (used by the real adapter).
RECOGNITION_OUTPUT_CONTRACT = {
    "items": [
        {
            "type": "one of: " + ", ".join(t.value for t in EquipmentType),
            "quantity": "integer >= 1",
            "load_min": "number or null (lightest load, lb)",
            "load_max": "number or null (heaviest load, lb)",
            "load_increment": "number or null (smallest step, lb)",
            "attributes": "object; e.g. {\"plate_denominations\":[45,25,10]}",
            "confidence": "number 0..1 — your certainty for THIS item",
        }
    ]
}


class EquipmentRecognizer(abc.ABC):
    """Provider-agnostic recognizer interface."""

    name: str = "base"

    @abc.abstractmethod
    async def recognize(self, image_bytes: list[bytes]) -> RecognitionResult:
        """Return a draft inventory from one or more images."""


class DevStubRecognizer(EquipmentRecognizer):
    """Deterministic stub so the capture/confirm flow is fully testable without a
    provider. Returns a plausible home-gym draft with mid-range confidences that
    a user would then correct."""

    name = "stub"

    async def recognize(self, image_bytes: list[bytes]) -> RecognitionResult:
        items = [
            RecognizedItem(
                type=EquipmentType.BARBELL, quantity=1,
                load_min=45, load_max=45, attributes={"bar_weight_lb": 45}, confidence=0.82,
            ),
            RecognizedItem(
                type=EquipmentType.PLATES, quantity=1,
                load_min=10, load_max=45,
                attributes={"plate_denominations": [45, 25, 10, 5], "pairs": True}, confidence=0.55,
            ),
            RecognizedItem(
                type=EquipmentType.ADJUSTABLE_DUMBBELLS, quantity=2,
                load_min=5, load_max=50, load_increment=5, confidence=0.6,
            ),
            RecognizedItem(
                type=EquipmentType.BENCH_ADJUSTABLE, quantity=1, confidence=0.74,
            ),
            RecognizedItem(
                type=EquipmentType.POWER_RACK, quantity=1,
                attributes={"has_pull_up_bar": True}, confidence=0.7,
            ),
        ]
        return RecognitionResult(items=items, recognizer=self.name)


# ----------------------------------------------------------------------------
# Bedrock + Claude multimodal (spec R1b)
# ----------------------------------------------------------------------------

# Tool the model is FORCED to call, so output is structured + schema-validated
# rather than free-text we have to parse heuristically.
SUBMIT_INVENTORY_TOOL = {
    "toolSpec": {
        "name": "submit_inventory",
        "description": "Report every distinct piece of weight-training equipment visible.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": [t.value for t in EquipmentType]},
                                "quantity": {"type": "integer", "minimum": 1},
                                "load_min": {"type": ["number", "null"]},
                                "load_max": {"type": ["number", "null"]},
                                "load_increment": {"type": ["number", "null"]},
                                "attributes": {"type": "object"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": ["type", "quantity", "confidence"],
                        },
                    }
                },
                "required": ["items"],
            }
        },
    }
}

_PROMPT = (
    "You are cataloguing home/garage gym equipment from photos. Identify every "
    "distinct piece of equipment. For plates and adjustable dumbbells, estimate "
    "load_min/load_max in pounds and note denominations in attributes, but set a "
    "LOW confidence for any weight you cannot actually read in the image — do not "
    "guess precise weights. Label cardio machines with their specific type "
    "(treadmill, rowing_machine, stationary_bike, elliptical) rather than 'other'. "
    "Call submit_inventory with your findings."
)


def _detect_image_format(data: bytes) -> str:
    """Sniff jpeg/png/webp from magic bytes (Bedrock requires the format field)."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpeg"


def parse_converse_tool_output(response: dict, recognizer_name: str) -> RecognitionResult:
    """Pure parser for a Bedrock Converse response: pull the forced tool-use input
    and coerce it into a validated RecognitionResult. Isolated from the network
    call so it can be unit-tested. Unknown types -> OTHER; confidence clamped."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_input = None
    for block in content:
        if "toolUse" in block and block["toolUse"].get("name") == "submit_inventory":
            tool_input = block["toolUse"].get("input", {})
            break
    if tool_input is None:
        return RecognitionResult(items=[], recognizer=recognizer_name)

    items: list[RecognizedItem] = []
    for raw in tool_input.get("items", []):
        t = raw.get("type", "")
        original = None
        if not is_valid_type(t):
            original, t = t, EquipmentType.OTHER.value
        attrs = raw.get("attributes") or {}
        if original:
            attrs = {**attrs, "model_reported_type": original}
        conf = raw.get("confidence", 0.0)
        try:
            conf = min(1.0, max(0.0, float(conf)))
        except (TypeError, ValueError):
            conf = 0.0
        items.append(RecognizedItem(
            type=EquipmentType(t),
            quantity=max(1, int(raw.get("quantity", 1) or 1)),
            load_min=raw.get("load_min"),
            load_max=raw.get("load_max"),
            load_increment=raw.get("load_increment"),
            attributes=attrs,
            confidence=conf,
        ))
    return RecognitionResult(items=items, recognizer=recognizer_name)


class BedrockClaudeRecognizer(EquipmentRecognizer):
    """Production recognizer: Claude multimodal via Bedrock Converse, with a
    forced tool call so the response is always schema-shaped JSON."""

    def __init__(self, settings):
        import boto3  # imported lazily so the stub path needs no AWS deps
        self._model_id = settings.bedrock_model_id
        self._max_tokens = settings.bedrock_max_tokens
        self.name = f"bedrock:{settings.bedrock_model_id}"
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def _invoke(self, image_bytes: list[bytes]) -> dict:
        """Synchronous Bedrock Converse call (run in a thread by recognize)."""
        content: list[dict] = [{"text": _PROMPT}]
        for data in image_bytes:
            content.append({
                "image": {"format": _detect_image_format(data), "source": {"bytes": data}}
            })
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": 0.0},
            toolConfig={
                "tools": [SUBMIT_INVENTORY_TOOL],
                "toolChoice": {"tool": {"name": "submit_inventory"}},
            },
        )

    async def recognize(self, image_bytes: list[bytes]) -> RecognitionResult:
        imgs = image_bytes[:4]  # cap payload — Bedrock returns nothing if combined images are too large
        response = await asyncio.to_thread(self._invoke, imgs)
        return parse_converse_tool_output(response, self.name)


_recognizer: EquipmentRecognizer | None = None


def build_recognizer(settings) -> EquipmentRecognizer:
    """Factory — branches on the locked provider (R1b)."""
    global _recognizer
    if _recognizer is None:
        if settings.vision_provider == "bedrock":
            _recognizer = BedrockClaudeRecognizer(settings)
        else:
            _recognizer = DevStubRecognizer()
    return _recognizer
