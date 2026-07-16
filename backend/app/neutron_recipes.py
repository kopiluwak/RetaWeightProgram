"""Neutron recipe generation (nutrition module).

Text-only Bedrock Converse calls with FORCED tool output (same structured-
output pattern as recognition.py / neutron_vision.py). Three entry points:

  generate_recipes(...)   3-5 recipe options maximizing use of pantry items
  regenerate_recipe(...)  "Make it Vegan/Vegetarian" — rebuild ONE recipe with
                          plant/veg proteins only, keeping pantry utilization
  generate_day_plan(...)  "Surprise Me" — a full day of meals hitting the
                          protein target under all restrictions

Dietary restrictions are passed as HARD constraints and re-validated after
parsing where cheaply possible (we never re-trust the model blindly).
Temperature 0.7 for variety — unlike vision, determinism isn't a virtue here.
"""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- schemas

VALID_DIFFICULTIES = ("easy", "medium", "hard")


class RecipeIngredient(BaseModel):
    """One ingredient line; from_pantry drives the pantry-utilization UI."""

    name: str
    quantity: str = ""            # "200 g", "1 can"
    from_pantry: bool = False     # true if it maps to a scanned/saved pantry item


class Recipe(BaseModel):
    """A complete generated recipe; macros are per serving."""

    title: str
    description: str = ""
    servings: int = Field(default=1, ge=1)
    prep_minutes: int = Field(default=10, ge=0)
    cook_minutes: int = Field(default=15, ge=0)
    difficulty: str = "easy"      # easy | medium | hard
    protein_g: float = Field(default=0, ge=0)   # PER SERVING
    calories: float = Field(default=0, ge=0)    # per serving
    carbs_g: float = Field(default=0, ge=0)
    fat_g: float = Field(default=0, ge=0)
    ingredients: list[RecipeIngredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)  # e.g. ["high-protein","vegan","keto"]
    is_vegan: bool = False
    is_vegetarian: bool = False


class RecipeBatch(BaseModel):
    """A set of recipe options plus which engine produced them."""

    recipes: list[Recipe]
    generator: str


class DayPlanMeal(BaseModel):
    """One meal slot in a Surprise Me day plan."""

    slot: str = "meal"            # breakfast | lunch | dinner | snack
    recipe: Recipe


class DayPlan(BaseModel):
    """A full day of meals with computed protein/calorie totals."""

    meals: list[DayPlanMeal]
    total_protein_g: float = 0
    total_calories: float = 0
    note: str = ""
    generator: str = ""


# ------------------------------------------------------------- tool specs

_RECIPE_JSON = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "servings": {"type": "integer", "minimum": 1},
        "prep_minutes": {"type": "integer", "minimum": 0},
        "cook_minutes": {"type": "integer", "minimum": 0},
        "difficulty": {"type": "string", "enum": list(VALID_DIFFICULTIES)},
        "protein_g": {"type": "number", "minimum": 0},
        "calories": {"type": "number", "minimum": 0},
        "carbs_g": {"type": "number", "minimum": 0},
        "fat_g": {"type": "number", "minimum": 0},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "string"},
                    "from_pantry": {"type": "boolean"},
                },
                "required": ["name"],
            },
        },
        "steps": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "is_vegan": {"type": "boolean"},
        "is_vegetarian": {"type": "boolean"},
    },
    "required": ["title", "servings", "protein_g", "calories", "ingredients", "steps"],
}

SUBMIT_RECIPES_TOOL = {
    "toolSpec": {
        "name": "submit_recipes",
        "description": "Submit the generated recipe options.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"recipes": {"type": "array", "items": _RECIPE_JSON}},
            "required": ["recipes"],
        }},
    }
}

SUBMIT_DAY_PLAN_TOOL = {
    "toolSpec": {
        "name": "submit_day_plan",
        "description": "Submit a full day of meals.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "meals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slot": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]},
                            "recipe": _RECIPE_JSON,
                        },
                        "required": ["slot", "recipe"],
                    },
                },
                "note": {"type": "string"},
            },
            "required": ["meals"],
        }},
    }
}

# --------------------------------------------------------------- prompts

_RESTRICTION_TEXT = {
    "no_garlic": "absolutely no garlic in any form (fresh, powder, granulated)",
    "no_onion": "absolutely no onion in any form (fresh, powder, shallots, leeks)",
    "no_red_meat": ("absolutely NO mammalian meat or by-products — no beef, pork, lamb, venison, "
                    "gelatin, lard, dairy-adjacent mammal products where flagged. This user may have "
                    "Alpha-Gal syndrome, so treat this as a life-safety allergy, not a preference. "
                    "Poultry and fish are fine unless another restriction excludes them"),
    "no_dairy": "no dairy of any kind (milk, cheese, yogurt, whey, butter, cream)",
    "keto": "keto: keep net carbs under ~10 g per serving",
    "low_carb": "low-carb: keep carbs under ~25 g per serving",
}

_DIET_TEXT = {
    "omnivore": "no diet-pattern limits beyond the restrictions listed",
    "vegetarian": "VEGETARIAN: no meat, poultry, or fish; eggs and dairy allowed unless restricted",
    "pescatarian": "PESCATARIAN: fish and seafood allowed; no other meat or poultry",
    "vegan": "VEGAN: plant foods only — no meat, fish, eggs, dairy, honey, or any animal product",
}


def _constraints_block(diet_pattern: str, restrictions: list[str]) -> str:
    """Render the diet pattern + every restriction as HARD-constraint prompt lines."""
    lines = [f"- Diet pattern: {_DIET_TEXT.get(diet_pattern, _DIET_TEXT['omnivore'])}"]
    for r in restrictions:
        if r.startswith("custom:"):
            lines.append(f"- HARD allergy/exclusion (user-declared): no {r[7:].strip()}")
        elif r in _RESTRICTION_TEXT:
            lines.append(f"- HARD constraint: {_RESTRICTION_TEXT[r]}")
    if not restrictions:
        lines.append("- No additional restrictions.")
    return "\n".join(lines)


def _pantry_block(pantry: list[dict]) -> str:
    """Render pantry items (with protein-density hints) as a prompt list."""
    if not pantry:
        return "(The user's pantry list is empty — use common, affordable ingredients.)"
    lines = []
    for p in pantry:
        q = f" ({p['quantity']})" if p.get("quantity") else ""
        d = f" [protein: {p.get('protein_density', 'low')}]"
        lines.append(f"- {p['name']}{q}{d}")
    return "\n".join(lines)


_BASE_PERSONA = (
    "You are the recipe engine of a fitness app for people on GLP-1 medications "
    "(reduced appetite, eating in a calorie deficit) who must hit a daily protein "
    "minimum to preserve muscle mass. Small appetites mean every bite has to "
    "count: favor PROTEIN-DENSE recipes with modest total volume, simple prep, "
    "and gentle, appealing flavors. Macros must be realistic — compute them from "
    "the actual ingredient quantities, per serving, and never overstate protein."
)


def build_recipes_prompt(pantry: list[dict], diet_pattern: str, restrictions: list[str],
                         protein_target_g: float | None, min_protein_per_serving: float,
                         count: int, extra_note: str = "") -> str:
    """Prompt for the main recipe-options generation call."""
    target = (f"The user's daily protein target is {protein_target_g:.0f} g."
              if protein_target_g else "The user's daily protein target is not set yet.")
    return (
        f"{_BASE_PERSONA}\n\n"
        f"{target}\n\n"
        f"USER'S AVAILABLE INGREDIENTS (use as many as possible — pantry utilization "
        f"is a core feature; mark those ingredients from_pantry=true):\n"
        f"{_pantry_block(pantry)}\n\n"
        f"DIETARY RULES (violating any of these is a critical failure):\n"
        f"{_constraints_block(diet_pattern, restrictions)}\n\n"
        f"Generate exactly {count} distinct recipe options. Every recipe must have "
        f"at least {min_protein_per_serving:.0f} g protein PER SERVING. Prefer "
        f"recipes that need zero or very few non-pantry ingredients; when you add "
        f"one, make it a cheap staple. Steps should be short, numbered-style "
        f"imperative sentences a tired person can follow. Include realistic "
        f"prep/cook minutes and a difficulty rating. Tag each recipe (e.g. "
        f"'high-protein', 'one-pan', '15-min', 'vegan'). {extra_note}\n"
        f"Call submit_recipes with the results."
    )


def build_veganize_prompt(recipe: dict, mode: str, pantry: list[dict],
                          restrictions: list[str]) -> str:
    """Prompt for rebuilding ONE recipe as vegan/vegetarian."""
    rule = _DIET_TEXT["vegan"] if mode == "vegan" else _DIET_TEXT["vegetarian"]
    return (
        f"{_BASE_PERSONA}\n\n"
        f"Rebuild the following recipe as a {mode.upper()} version. Keep the spirit, "
        f"format and rough macros of the original but replace all non-compliant "
        f"ingredients with {'plant proteins only (tofu, tempeh, seitan, legumes, plant yogurts)' if mode == 'vegan' else 'vegetarian proteins (eggs, dairy, tofu, tempeh, legumes)'}. "
        f"Protein per serving must stay within 20% of the original or higher.\n\n"
        f"ORIGINAL RECIPE (JSON):\n{recipe}\n\n"
        f"STILL AVAILABLE PANTRY ITEMS (reuse compliant ones, from_pantry=true):\n"
        f"{_pantry_block(pantry)}\n\n"
        f"DIETARY RULES:\n- {rule}\n"
        f"{_constraints_block('omnivore', restrictions)}\n\n"
        f"Call submit_recipes with exactly ONE recipe."
    )


def build_day_plan_prompt(pantry: list[dict], diet_pattern: str, restrictions: list[str],
                          protein_target_g: float) -> str:
    """Prompt for the Surprise Me full-day plan."""
    return (
        f"{_BASE_PERSONA}\n\n"
        f"Design ONE full day of eating (3 meals + 1-2 optional snacks) that sums "
        f"to AT LEAST {protein_target_g:.0f} g protein for the day, spread so no "
        f"single meal is overwhelming for a small GLP-1 appetite (roughly 25-40 g "
        f"per meal). Use the user's pantry first.\n\n"
        f"USER'S AVAILABLE INGREDIENTS:\n{_pantry_block(pantry)}\n\n"
        f"DIETARY RULES (hard constraints):\n"
        f"{_constraints_block(diet_pattern, restrictions)}\n\n"
        f"Add a one-sentence encouraging note for the day. "
        f"Call submit_day_plan with the results."
    )


# --------------------------------------------------------------- parsing


def _coerce_recipe(raw: dict) -> Recipe | None:
    """Defensively coerce one raw recipe dict into a validated Recipe.
    Returns None (drop the recipe) rather than raising on malformed input."""
    try:
        title = str(raw.get("title", "")).strip()
        if not title:
            return None
        difficulty = raw.get("difficulty", "easy")
        if difficulty not in VALID_DIFFICULTIES:
            difficulty = "easy"
        ings = []
        for i in raw.get("ingredients", []) or []:
            name = str(i.get("name", "")).strip()
            if name:
                ings.append(RecipeIngredient(
                    name=name[:120],
                    quantity=str(i.get("quantity", "") or "")[:60],
                    from_pantry=bool(i.get("from_pantry", False)),
                ))
        steps = [str(s).strip() for s in (raw.get("steps") or []) if str(s).strip()]
        return Recipe(
            title=title[:160],
            description=str(raw.get("description", "") or "")[:500],
            servings=max(1, int(raw.get("servings", 1) or 1)),
            prep_minutes=max(0, int(raw.get("prep_minutes", 10) or 0)),
            cook_minutes=max(0, int(raw.get("cook_minutes", 15) or 0)),
            difficulty=difficulty,
            protein_g=max(0.0, float(raw.get("protein_g", 0) or 0)),
            calories=max(0.0, float(raw.get("calories", 0) or 0)),
            carbs_g=max(0.0, float(raw.get("carbs_g", 0) or 0)),
            fat_g=max(0.0, float(raw.get("fat_g", 0) or 0)),
            ingredients=ings,
            steps=steps,
            tags=[str(t)[:30] for t in (raw.get("tags") or [])][:8],
            is_vegan=bool(raw.get("is_vegan", False)),
            is_vegetarian=bool(raw.get("is_vegetarian", False)) or bool(raw.get("is_vegan", False)),
        )
    except (TypeError, ValueError):
        return None


def parse_recipes_tool_output(response: dict, generator: str) -> RecipeBatch:
    """Pure parser for the submit_recipes forced tool call (unit-testable)."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_input = None
    for block in content:
        if "toolUse" in block and block["toolUse"].get("name") == "submit_recipes":
            tool_input = block["toolUse"].get("input", {})
            break
    if tool_input is None:
        return RecipeBatch(recipes=[], generator=generator)
    recipes = [r for r in (_coerce_recipe(x) for x in tool_input.get("recipes", [])) if r]
    return RecipeBatch(recipes=recipes, generator=generator)


def parse_day_plan_tool_output(response: dict, generator: str) -> DayPlan:
    """Pure parser for submit_day_plan; totals are recomputed server-side."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_input = None
    for block in content:
        if "toolUse" in block and block["toolUse"].get("name") == "submit_day_plan":
            tool_input = block["toolUse"].get("input", {})
            break
    if tool_input is None:
        return DayPlan(meals=[], generator=generator)
    meals: list[DayPlanMeal] = []
    for m in tool_input.get("meals", []):
        recipe = _coerce_recipe(m.get("recipe") or {})
        if recipe is None:
            continue
        slot = m.get("slot", "meal")
        if slot not in ("breakfast", "lunch", "dinner", "snack"):
            slot = "meal"
        meals.append(DayPlanMeal(slot=slot, recipe=recipe))
    total_p = sum(m.recipe.protein_g * m.recipe.servings for m in meals)
    total_c = sum(m.recipe.calories * m.recipe.servings for m in meals)
    return DayPlan(meals=meals, total_protein_g=round(total_p, 1),
                   total_calories=round(total_c), note=str(tool_input.get("note", "") or "")[:300],
                   generator=generator)


# --------------------------------------------------------------- engines


class DevStubRecipeEngine:
    """Deterministic recipes so the whole flow works without AWS."""

    name = "stub"

    def _stub_recipe(self, n: int, vegan: bool) -> Recipe:
        if vegan:
            return Recipe(
                title=f"Crispy Tofu & Black Bean Bowl #{n}",
                description="Pan-crisped tofu over seasoned black beans and spinach.",
                servings=2, prep_minutes=10, cook_minutes=15, difficulty="easy",
                protein_g=32, calories=430, carbs_g=35, fat_g=16,
                ingredients=[
                    RecipeIngredient(name="extra-firm tofu", quantity="350 g", from_pantry=False),
                    RecipeIngredient(name="canned black beans", quantity="1 can", from_pantry=True),
                    RecipeIngredient(name="spinach", quantity="2 handfuls", from_pantry=True),
                ],
                steps=["Press and cube the tofu.", "Pan-fry until golden.",
                       "Warm the beans with cumin.", "Wilt spinach, assemble the bowl."],
                tags=["high-protein", "vegan", "one-pan"], is_vegan=True, is_vegetarian=True,
            )
        return Recipe(
            title=f"Sheet-Pan Chicken & Greek Yogurt Ranch #{n}",
            description="Juicy chicken breast with a cool protein-packed yogurt sauce.",
            servings=2, prep_minutes=10, cook_minutes=20, difficulty="easy",
            protein_g=45, calories=420, carbs_g=12, fat_g=14,
            ingredients=[
                RecipeIngredient(name="chicken breast", quantity="450 g", from_pantry=True),
                RecipeIngredient(name="Greek yogurt (plain)", quantity="150 g", from_pantry=True),
                RecipeIngredient(name="spinach", quantity="2 handfuls", from_pantry=True),
            ],
            steps=["Season chicken, roast at 220°C for 18-20 min.",
                   "Stir herbs into the yogurt.", "Slice, serve over spinach with the sauce."],
            tags=["high-protein", "30g-club", "sheet-pan"],
        )

    async def generate(self, prompt: str, tool: dict) -> dict:  # signature parity
        raise NotImplementedError

    async def recipes(self, prompt: str, count: int, vegan_hint: bool) -> RecipeBatch:
        return RecipeBatch(
            recipes=[self._stub_recipe(i + 1, vegan_hint) for i in range(count)],
            generator=self.name,
        )

    async def day_plan(self, prompt: str, target: float) -> DayPlan:
        meals = [
            DayPlanMeal(slot="breakfast", recipe=self._stub_recipe(1, False)),
            DayPlanMeal(slot="lunch", recipe=self._stub_recipe(2, True)),
            DayPlanMeal(slot="dinner", recipe=self._stub_recipe(3, False)),
        ]
        total_p = sum(m.recipe.protein_g * m.recipe.servings for m in meals)
        return DayPlan(meals=meals, total_protein_g=total_p,
                       total_calories=sum(m.recipe.calories * m.recipe.servings for m in meals),
                       note="Stub plan — every gram counts today!", generator=self.name)


class BedrockClaudeRecipeEngine:
    """Production engine: text-only Bedrock Converse with forced tool output."""

    def __init__(self, settings):
        import boto3
        self._model_id = settings.bedrock_model_id
        self._max_tokens = max(settings.bedrock_max_tokens, 4096)  # recipes are long
        self.name = f"bedrock:{settings.bedrock_model_id}"
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def _invoke(self, prompt: str, tool: dict, tool_name: str) -> dict:
        """Synchronous Bedrock Converse call (run in a thread by the callers)."""
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": 0.7},
            toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": tool_name}}},
        )

    async def recipes(self, prompt: str, count: int, vegan_hint: bool) -> RecipeBatch:
        response = await asyncio.to_thread(self._invoke, prompt, SUBMIT_RECIPES_TOOL, "submit_recipes")
        return parse_recipes_tool_output(response, self.name)

    async def day_plan(self, prompt: str, target: float) -> DayPlan:
        response = await asyncio.to_thread(self._invoke, prompt, SUBMIT_DAY_PLAN_TOOL, "submit_day_plan")
        return parse_day_plan_tool_output(response, self.name)


_engine = None


def build_recipe_engine(settings):
    """Build (once) and return the engine selected by settings.vision_provider."""
    global _engine
    if _engine is None:
        if settings.vision_provider == "bedrock":
            _engine = BedrockClaudeRecipeEngine(settings)
        else:
            _engine = DevStubRecipeEngine()
    return _engine
