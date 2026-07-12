"""Neutron nutrition router (Increment 5).

  GET  /nutrition/profile            protein profile (auto-created on first read)
  PUT  /nutrition/profile            edit weight/goal/target/diet/restrictions
  POST /nutrition/weight             log bodyweight (auto-recalcs target in auto mode)
  GET  /nutrition/weight             bodyweight history
  POST /nutrition/pantry/scan        photos -> DRAFT food list (photos never stored)
  GET  /nutrition/pantry             current saved pantry
  PUT  /nutrition/pantry             replace pantry with user-confirmed list
  POST /nutrition/recipes/generate   3-5 high-protein recipes from pantry + filters
  POST /nutrition/recipes/adapt      "Make it Vegan/Vegetarian" for one recipe
  POST /nutrition/recipes/surprise   full-day plan hitting the protein target
  GET/POST/DELETE /nutrition/recipes/saved
  POST /nutrition/log                log protein intake (returns newly earned badges)
  GET  /nutrition/summary            everything the dashboard needs, one payload
  GET  /nutrition/marketplace        curated protein boosters (affiliate placeholders)

Day/week bucketing uses `tz` = minutes east of UTC, exactly like /analytics.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import (
    NutritionBadge,
    NutritionProfile,
    PantryItem,
    ProteinLog,
    SavedRecipe,
    User,
    WeightLog,
)
from ..neutron_gamification import (
    BADGES,
    best_streak,
    current_streak,
    evaluate_badges,
    level_for,
    motivation,
    muscle_score,
    total_hit_days,
    weekly_streak,
)
from ..neutron_recipes import (
    DayPlan,
    Recipe,
    build_day_plan_prompt,
    build_recipe_engine,
    build_recipes_prompt,
    build_veganize_prompt,
)
from ..neutron_vision import ScannedFoodItem, build_pantry_scanner

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

GRAMS_PER_KG = 1.0          # spec: minimum 1 g protein / kg bodyweight / day
MAX_CUSTOM_RESTRICTIONS = 20


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _local_date(ts: dt.datetime, tz_minutes: int) -> dt.date:
    return (ts + dt.timedelta(minutes=tz_minutes)).date()


# ------------------------------------------------------------------ schemas


class ProfileOut(BaseModel):
    current_weight_kg: float | None
    goal_weight_kg: float | None
    protein_target_g: float | None
    target_mode: str
    diet_pattern: str
    restrictions: list[str]
    onboarded: bool


class ProfileIn(BaseModel):
    current_weight_kg: float | None = Field(default=None, gt=20, lt=400)
    goal_weight_kg: float | None = Field(default=None, gt=20, lt=400)
    # None -> auto (1 g/kg); a number pins a custom target.
    protein_target_g: float | None = Field(default=None, gt=0, lt=500)
    diet_pattern: str = "omnivore"
    restrictions: list[str] = Field(default_factory=list)


class WeightIn(BaseModel):
    weight_kg: float = Field(gt=20, lt=400)


class WeightOut(BaseModel):
    weight_kg: float
    logged_at: str


class PantryItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: str = Field(default="", max_length=60)
    category: str = "pantry"
    protein_per_100g: float | None = None
    protein_density: str = "low"
    source: str = "manual"
    confidence: float | None = None


class PantryItemOut(PantryItemIn):
    id: str


class PantryReplaceIn(BaseModel):
    items: list[PantryItemIn] = Field(max_length=200)


class ScanOut(BaseModel):
    items: list[ScannedFoodItem]
    recognizer: str


class GenerateRecipesIn(BaseModel):
    use_pantry: bool = True
    count: int = Field(default=4, ge=3, le=5)
    min_protein_per_serving: float = Field(default=30, ge=10, le=100)
    # Optional per-request overrides; profile values apply when omitted.
    diet_pattern: str | None = None
    extra_restrictions: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=300)  # freeform, e.g. "something cold"


class RecipesOut(BaseModel):
    recipes: list[Recipe]
    generator: str
    newly_earned_badges: list[str] = Field(default_factory=list)


class AdaptRecipeIn(BaseModel):
    recipe: Recipe
    mode: str = Field(pattern="^(vegan|vegetarian)$")


class SaveRecipeIn(BaseModel):
    recipe: Recipe
    source: str = "builder"


class SavedRecipeOut(BaseModel):
    id: str
    title: str
    protein_g: float
    calories: float
    recipe: Recipe
    source: str
    created_at: str


class LogIn(BaseModel):
    grams: float = Field(gt=0, le=400)
    calories: float | None = Field(default=None, ge=0, le=5000)
    label: str = Field(default="", max_length=160)
    source: str = "quick_add"


class LogEntryOut(BaseModel):
    id: str
    grams: float
    calories: float | None
    label: str
    source: str
    logged_at: str


class LogOut(BaseModel):
    entry: LogEntryOut
    today_total_g: float
    target_g: float | None
    pct_of_target: float | None
    newly_earned_badges: list[str]
    message: str


class DayBar(BaseModel):
    date: str
    grams: float
    hit: bool


class WeekAvg(BaseModel):
    week_start: str
    avg_grams: float


class BadgeOut(BaseModel):
    key: str
    name: str
    description: str
    earned: bool
    awarded_at: str | None


class SummaryOut(BaseModel):
    target_g: float | None
    today_g: float
    today_pct: float | None
    week_days: list[DayBar]           # trailing 7, oldest first
    week_avg_g: float
    trend_weeks: list[WeekAvg]        # trailing 4 calendar weeks, oldest first
    daily_streak: int
    best_daily_streak: int
    weekly_streak: int
    total_hit_days: int
    level: int
    level_title: str
    next_level_at: int | None
    muscle_score: int
    badges: list[BadgeOut]
    message: str


class MarketItem(BaseModel):
    name: str
    brand: str
    category: str
    protein_per_serving_g: float
    serving: str
    price_usd: float
    tags: list[str]
    url: str
    url_is_placeholder: bool = True


class MarketplaceOut(BaseModel):
    items: list[MarketItem]
    disclosure: str


# ------------------------------------------------------------------ helpers


async def _get_or_create_profile(db: AsyncSession, user_id: str) -> NutritionProfile:
    prof = (await db.execute(
        select(NutritionProfile).where(NutritionProfile.user_id == user_id)
    )).scalar_one_or_none()
    if prof is None:
        prof = NutritionProfile(user_id=user_id)
        db.add(prof)
        await db.flush()
    return prof


def _auto_target(weight_kg: float | None) -> float | None:
    return round(weight_kg * GRAMS_PER_KG, 1) if weight_kg else None


def _profile_out(p: NutritionProfile) -> ProfileOut:
    return ProfileOut(
        current_weight_kg=p.current_weight_kg, goal_weight_kg=p.goal_weight_kg,
        protein_target_g=p.protein_target_g, target_mode=p.target_mode,
        diet_pattern=p.diet_pattern, restrictions=list(p.restrictions or []),
        onboarded=p.onboarded,
    )


VALID_DIET_PATTERNS = ("omnivore", "vegetarian", "pescatarian", "vegan")
KNOWN_RESTRICTIONS = ("no_garlic", "no_onion", "no_red_meat", "no_dairy", "keto", "low_carb")


def _clean_restrictions(raw: list[str]) -> list[str]:
    out: list[str] = []
    for r in raw[:MAX_CUSTOM_RESTRICTIONS]:
        r = r.strip()
        if r in KNOWN_RESTRICTIONS or (r.startswith("custom:") and len(r) > 7):
            if r not in out:
                out.append(r)
    return out


async def _day_grams(db: AsyncSession, user_id: str, tz: int,
                     since_days: int = 400) -> dict[dt.date, float]:
    cutoff = _now() - dt.timedelta(days=since_days)
    rows = (await db.execute(
        select(ProteinLog.grams, ProteinLog.logged_at)
        .where(ProteinLog.user_id == user_id, ProteinLog.logged_at >= cutoff)
    )).all()
    acc: dict[dt.date, float] = {}
    for grams, ts in rows:
        d = _local_date(ts, tz)
        acc[d] = acc.get(d, 0.0) + grams
    return acc


async def _earned_badges(db: AsyncSession, user_id: str) -> dict[str, dt.datetime]:
    rows = (await db.execute(
        select(NutritionBadge).where(NutritionBadge.user_id == user_id)
    )).scalars().all()
    return {b.badge_key: b.awarded_at for b in rows}


async def _award(db: AsyncSession, user_id: str, keys: list[str]) -> None:
    for k in keys:
        db.add(NutritionBadge(user_id=user_id, badge_key=k))


async def _check_and_award_badges(db: AsyncSession, user: User, prof: NutritionProfile,
                                  tz: int) -> list[str]:
    """Run streak/threshold badges after any log; returns newly earned keys."""
    day_grams = await _day_grams(db, user.id, tz)
    already = set((await _earned_badges(db, user.id)).keys())
    max_single = (await db.execute(
        select(ProteinLog.grams).where(ProteinLog.user_id == user.id)
        .order_by(ProteinLog.grams.desc()).limit(1)
    )).scalar_one_or_none() or 0.0
    weight_rows = (await db.execute(
        select(WeightLog.logged_at).where(WeightLog.user_id == user.id)
    )).scalars().all()
    weeks = {(_local_date(ts, tz) - dt.timedelta(days=_local_date(ts, tz).weekday()))
             for ts in weight_rows}
    weight_streak = 0
    ws = _local_date(_now(), tz)
    ws -= dt.timedelta(days=ws.weekday())
    while ws in weeks:
        weight_streak += 1
        ws -= dt.timedelta(days=7)
    new = evaluate_badges(
        day_grams=day_grams, target=prof.protein_target_g or 0.0,
        today=_local_date(_now(), tz), has_any_log=bool(day_grams) or max_single > 0,
        max_single_log_g=max_single, restrictions=list(prof.restrictions or []),
        diet_pattern=prof.diet_pattern, weight_log_weeks=weight_streak, already=already,
    )
    await _award(db, user.id, new)
    return new


# ------------------------------------------------------------------ profile


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prof = await _get_or_create_profile(db, user.id)
    await db.commit()
    return _profile_out(prof)


@router.put("/profile", response_model=ProfileOut)
async def put_profile(body: ProfileIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if body.diet_pattern not in VALID_DIET_PATTERNS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown diet pattern: {body.diet_pattern}")
    prof = await _get_or_create_profile(db, user.id)
    weight_changed = (body.current_weight_kg is not None
                      and body.current_weight_kg != prof.current_weight_kg)
    prof.current_weight_kg = body.current_weight_kg
    prof.goal_weight_kg = body.goal_weight_kg
    prof.diet_pattern = body.diet_pattern
    prof.restrictions = _clean_restrictions(body.restrictions)
    if body.protein_target_g is not None:
        prof.target_mode = "custom"
        prof.protein_target_g = round(body.protein_target_g, 1)
    else:
        prof.target_mode = "auto"
        prof.protein_target_g = _auto_target(prof.current_weight_kg)
    prof.onboarded = prof.current_weight_kg is not None
    if weight_changed and body.current_weight_kg is not None:
        db.add(WeightLog(user_id=user.id, weight_kg=body.current_weight_kg))
    await db.commit()
    return _profile_out(prof)


# ------------------------------------------------------------------ weight


@router.post("/weight", response_model=ProfileOut)
async def log_weight(body: WeightIn, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    prof = await _get_or_create_profile(db, user.id)
    db.add(WeightLog(user_id=user.id, weight_kg=body.weight_kg))
    prof.current_weight_kg = body.weight_kg
    if prof.target_mode == "auto":
        prof.protein_target_g = _auto_target(body.weight_kg)
    await db.commit()
    return _profile_out(prof)


@router.get("/weight", response_model=list[WeightOut])
async def weight_history(days: int = Query(default=180, ge=1, le=730),
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    cutoff = _now() - dt.timedelta(days=days)
    rows = (await db.execute(
        select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_at >= cutoff)
        .order_by(WeightLog.logged_at)
    )).scalars().all()
    return [WeightOut(weight_kg=w.weight_kg, logged_at=w.logged_at.isoformat()) for w in rows]


# ------------------------------------------------------------------ pantry


@router.post("/pantry/scan", response_model=ScanOut)
async def scan_pantry(images: list[UploadFile] = File(...),
                      user: User = Depends(get_current_user),
                      settings: Settings = Depends(get_settings)):
    """Photos in -> draft item list out. Nothing is persisted here and the
    images are discarded after the model call (module privacy promise)."""
    if not images:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one image required")
    raw = [await img.read() for img in images]
    scanner = build_pantry_scanner(settings)
    result = await scanner.scan(raw)
    return ScanOut(items=result.items, recognizer=result.recognizer)


@router.get("/pantry", response_model=list[PantryItemOut])
async def get_pantry(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(PantryItem).where(PantryItem.user_id == user.id).order_by(PantryItem.created_at)
    )).scalars().all()
    return [PantryItemOut(
        id=p.id, name=p.name, quantity=p.quantity, category=p.category,
        protein_per_100g=p.protein_per_100g, protein_density=p.protein_density,
        source=p.source, confidence=p.confidence,
    ) for p in rows]


@router.put("/pantry", response_model=list[PantryItemOut])
async def replace_pantry(body: PantryReplaceIn, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Replace the pantry with the user-confirmed list (the confirm step of the
    scan flow, and also plain manual editing)."""
    await db.execute(delete(PantryItem).where(PantryItem.user_id == user.id))
    for it in body.items:
        category = it.category if it.category in ("pantry", "fridge", "freezer", "other") else "other"
        density = it.protein_density if it.protein_density in ("high", "medium", "low") else "low"
        db.add(PantryItem(
            user_id=user.id, name=it.name.strip()[:120], quantity=it.quantity[:60],
            category=category, protein_per_100g=it.protein_per_100g,
            protein_density=density, source=it.source if it.source in ("scan", "manual") else "manual",
            confidence=it.confidence,
        ))
    await db.commit()
    return await get_pantry(user, db)  # type: ignore[arg-type]


# ------------------------------------------------------------------ recipes


async def _pantry_dicts(db: AsyncSession, user_id: str) -> list[dict]:
    rows = (await db.execute(
        select(PantryItem).where(PantryItem.user_id == user_id)
    )).scalars().all()
    return [{"name": p.name, "quantity": p.quantity, "protein_density": p.protein_density}
            for p in rows]


@router.post("/recipes/generate", response_model=RecipesOut)
async def generate_recipes(body: GenerateRecipesIn, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db),
                           settings: Settings = Depends(get_settings)):
    prof = await _get_or_create_profile(db, user.id)
    pantry = await _pantry_dicts(db, user.id) if body.use_pantry else []
    diet = body.diet_pattern if body.diet_pattern in VALID_DIET_PATTERNS else prof.diet_pattern
    restrictions = _clean_restrictions(list(prof.restrictions or []) + body.extra_restrictions)
    prompt = build_recipes_prompt(
        pantry=pantry, diet_pattern=diet, restrictions=restrictions,
        protein_target_g=prof.protein_target_g,
        min_protein_per_serving=body.min_protein_per_serving,
        count=body.count, extra_note=body.note,
    )
    engine = build_recipe_engine(settings)
    batch = await engine.recipes(prompt, body.count, vegan_hint=(diet == "vegan"))
    if not batch.recipes:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Recipe generation returned nothing — try again")

    # Event badge: first recipes generated from a scanned pantry.
    new_badges: list[str] = []
    if body.use_pantry and pantry:
        already = await _earned_badges(db, user.id)
        if "pantry_alchemist" not in already:
            await _award(db, user.id, ["pantry_alchemist"])
            new_badges.append("pantry_alchemist")
        await db.commit()
    return RecipesOut(recipes=batch.recipes, generator=batch.generator,
                      newly_earned_badges=new_badges)


@router.post("/recipes/adapt", response_model=RecipesOut)
async def adapt_recipe(body: AdaptRecipeIn, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    """'Make it Vegan / Vegetarian' — rebuild one recipe with compliant proteins."""
    prof = await _get_or_create_profile(db, user.id)
    pantry = await _pantry_dicts(db, user.id)
    prompt = build_veganize_prompt(
        recipe=body.recipe.model_dump(mode="json"), mode=body.mode,
        pantry=pantry, restrictions=list(prof.restrictions or []),
    )
    engine = build_recipe_engine(settings)
    batch = await engine.recipes(prompt, 1, vegan_hint=(body.mode == "vegan"))
    if not batch.recipes:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Adaptation failed — try again")
    return RecipesOut(recipes=batch.recipes[:1], generator=batch.generator)


@router.post("/recipes/surprise", response_model=DayPlan)
async def surprise_me(user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db),
                      settings: Settings = Depends(get_settings)):
    prof = await _get_or_create_profile(db, user.id)
    if not prof.protein_target_g:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Set your weight first so we know your protein target")
    pantry = await _pantry_dicts(db, user.id)
    prompt = build_day_plan_prompt(
        pantry=pantry, diet_pattern=prof.diet_pattern,
        restrictions=list(prof.restrictions or []), protein_target_g=prof.protein_target_g,
    )
    engine = build_recipe_engine(settings)
    plan = await engine.day_plan(prompt, prof.protein_target_g)
    if not plan.meals:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Plan generation returned nothing — try again")
    already = await _earned_badges(db, user.id)
    if "surprise_seeker" not in already:
        await _award(db, user.id, ["surprise_seeker"])
        await db.commit()
    return plan


@router.get("/recipes/saved", response_model=list[SavedRecipeOut])
async def list_saved(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(SavedRecipe).where(SavedRecipe.user_id == user.id)
        .order_by(SavedRecipe.created_at.desc())
    )).scalars().all()
    return [SavedRecipeOut(
        id=r.id, title=r.title, protein_g=r.protein_g, calories=r.calories,
        recipe=Recipe(**r.payload), source=r.source, created_at=r.created_at.isoformat(),
    ) for r in rows]


@router.post("/recipes/saved", response_model=SavedRecipeOut)
async def save_recipe(body: SaveRecipeIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    r = SavedRecipe(
        user_id=user.id, title=body.recipe.title, protein_g=body.recipe.protein_g,
        calories=body.recipe.calories, payload=body.recipe.model_dump(mode="json"),
        source=body.source if body.source in ("pantry_scan", "builder", "surprise") else "builder",
    )
    db.add(r)
    await db.commit()
    return SavedRecipeOut(id=r.id, title=r.title, protein_g=r.protein_g, calories=r.calories,
                          recipe=body.recipe, source=r.source, created_at=r.created_at.isoformat())


@router.delete("/recipes/saved/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved(recipe_id: str, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    r = (await db.execute(
        select(SavedRecipe).where(SavedRecipe.id == recipe_id, SavedRecipe.user_id == user.id)
    )).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    await db.delete(r)
    await db.commit()


# ------------------------------------------------------------------ logging


@router.post("/log", response_model=LogOut)
async def log_protein(body: LogIn, tz: int = Query(default=0, ge=-840, le=840),
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    prof = await _get_or_create_profile(db, user.id)
    entry = ProteinLog(
        user_id=user.id, grams=round(body.grams, 1), calories=body.calories,
        label=body.label.strip()[:160],
        source=body.source if body.source in ("recipe", "quick_add", "booster") else "quick_add",
    )
    db.add(entry)
    await db.flush()

    new_badges = await _check_and_award_badges(db, user, prof, tz)
    await db.commit()

    day_grams = await _day_grams(db, user.id, tz, since_days=2)
    today_total = day_grams.get(_local_date(_now(), tz), 0.0)
    target = prof.protein_target_g
    return LogOut(
        entry=LogEntryOut(id=entry.id, grams=entry.grams, calories=entry.calories,
                          label=entry.label, source=entry.source,
                          logged_at=entry.logged_at.isoformat()),
        today_total_g=round(today_total, 1), target_g=target,
        pct_of_target=round(100 * today_total / target, 1) if target else None,
        newly_earned_badges=new_badges,
        message=motivation(today_total, target or 0.0),
    )


@router.get("/log", response_model=list[LogEntryOut])
async def log_history(days: int = Query(default=7, ge=1, le=90),
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    cutoff = _now() - dt.timedelta(days=days)
    rows = (await db.execute(
        select(ProteinLog).where(ProteinLog.user_id == user.id, ProteinLog.logged_at >= cutoff)
        .order_by(ProteinLog.logged_at.desc())
    )).scalars().all()
    return [LogEntryOut(id=e.id, grams=e.grams, calories=e.calories, label=e.label,
                        source=e.source, logged_at=e.logged_at.isoformat()) for e in rows]


@router.delete("/log/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(entry_id: str, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    e = (await db.execute(
        select(ProteinLog).where(ProteinLog.id == entry_id, ProteinLog.user_id == user.id)
    )).scalar_one_or_none()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found")
    await db.delete(e)
    await db.commit()


# ------------------------------------------------------------------ summary


@router.get("/summary", response_model=SummaryOut)
async def summary(tz: int = Query(default=0, ge=-840, le=840),
                  user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    prof = await _get_or_create_profile(db, user.id)
    target = prof.protein_target_g or 0.0
    today = _local_date(_now(), tz)
    day_grams = await _day_grams(db, user.id, tz)

    # Trailing 7 days, oldest first.
    week_days = []
    for i in range(6, -1, -1):
        d = today - dt.timedelta(days=i)
        g = round(day_grams.get(d, 0.0), 1)
        week_days.append(DayBar(date=d.isoformat(), grams=g,
                                hit=target > 0 and g >= 0.9 * target))

    # Trailing 4 calendar weeks (Mon-based), oldest first; average over days
    # elapsed in the week (so the current week isn't diluted by the future).
    trend: list[WeekAvg] = []
    this_ws = today - dt.timedelta(days=today.weekday())
    for w in range(3, -1, -1):
        ws = this_ws - dt.timedelta(days=7 * w)
        n_days = (today - ws).days + 1 if ws == this_ws else 7
        total = sum(day_grams.get(ws + dt.timedelta(days=i), 0.0) for i in range(n_days))
        trend.append(WeekAvg(week_start=ws.isoformat(),
                             avg_grams=round(total / max(1, n_days), 1)))

    today_g = round(day_grams.get(today, 0.0), 1)
    hit_days = total_hit_days(day_grams, target)
    lvl, title, nxt = level_for(hit_days)
    earned = await _earned_badges(db, user.id)
    badges = [BadgeOut(
        key=k, name=n, description=desc, earned=k in earned,
        awarded_at=earned[k].isoformat() if k in earned else None,
    ) for k, (n, desc) in BADGES.items()]

    week_total = sum(b.grams for b in week_days)
    return SummaryOut(
        target_g=prof.protein_target_g, today_g=today_g,
        today_pct=round(100 * today_g / target, 1) if target else None,
        week_days=week_days, week_avg_g=round(week_total / 7, 1),
        trend_weeks=trend,
        daily_streak=current_streak(day_grams, target, today),
        best_daily_streak=best_streak(day_grams, target),
        weekly_streak=weekly_streak(day_grams, target, today),
        total_hit_days=hit_days,
        level=lvl, level_title=title, next_level_at=nxt,
        muscle_score=muscle_score(day_grams, target, today),
        badges=badges,
        message=motivation(today_g, target),
    )


# --------------------------------------------------------------- marketplace

# Curated static list. Product/protein/price data is real as of writing; the
# links are CLEARLY-LABELED placeholders to be swapped for affiliate URLs.
_MARKETPLACE: list[MarketItem] = [
    MarketItem(name="Gold Standard 100% Whey", brand="Optimum Nutrition", category="protein_powder",
               protein_per_serving_g=24, serving="1 scoop (30 g)", price_usd=37.99,
               tags=["Best for GLP-1 users", "easy to sip", "24 g/scoop"],
               url="https://example.com/affiliate-placeholder/on-gold-standard"),
    MarketItem(name="Clear Whey Isolate", brand="Myprotein", category="protein_powder",
               protein_per_serving_g=20, serving="1 scoop (25 g)", price_usd=29.99,
               tags=["Best for GLP-1 users", "juice-like, not milky", "light on the stomach"],
               url="https://example.com/affiliate-placeholder/myprotein-clear"),
    MarketItem(name="Pea Protein Isolate", brand="NOW Sports", category="protein_powder",
               protein_per_serving_g=24, serving="1 scoop (33 g)", price_usd=24.99,
               tags=["vegan", "unflavored", "24 g/scoop"],
               url="https://example.com/affiliate-placeholder/now-pea-protein"),
    MarketItem(name="Triple Zero Greek Yogurt", brand="Oikos", category="dairy",
               protein_per_serving_g=15, serving="1 cup (150 g)", price_usd=1.49,
               tags=["Best for GLP-1 users", "small volume, big protein", "no added sugar"],
               url="https://example.com/affiliate-placeholder/oikos-triple-zero"),
    MarketItem(name="Low-Fat Cottage Cheese", brand="Good Culture", category="dairy",
               protein_per_serving_g=14, serving="1/2 cup (110 g)", price_usd=2.99,
               tags=["whole food", "14 g per half-cup"],
               url="https://example.com/affiliate-placeholder/good-culture"),
    MarketItem(name="Protein Bar (Chocolate Sea Salt)", brand="RXBAR", category="bar",
               protein_per_serving_g=12, serving="1 bar (52 g)", price_usd=2.49,
               tags=["whole-food ingredients", "no whey"],
               url="https://example.com/affiliate-placeholder/rxbar"),
    MarketItem(name="Quest Protein Bar", brand="Quest Nutrition", category="bar",
               protein_per_serving_g=20, serving="1 bar (60 g)", price_usd=2.79,
               tags=["Best for GLP-1 users", "keto-friendly", "20 g/bar"],
               url="https://example.com/affiliate-placeholder/quest-bar"),
    MarketItem(name="Fairlife Core Power Elite", brand="Fairlife", category="ready_to_drink",
               protein_per_serving_g=42, serving="1 bottle (414 ml)", price_usd=3.99,
               tags=["Best for GLP-1 users", "42 g in one bottle", "lactose-free"],
               url="https://example.com/affiliate-placeholder/core-power-elite"),
    MarketItem(name="Wild-Caught Tuna Pouch", brand="Safe Catch", category="ready_to_eat",
               protein_per_serving_g=16, serving="1 pouch (74 g)", price_usd=2.29,
               tags=["shelf-stable", "zero prep"],
               url="https://example.com/affiliate-placeholder/safe-catch-tuna"),
    MarketItem(name="Roasted Edamame", brand="The Only Bean", category="snack",
               protein_per_serving_g=14, serving="1/3 cup (30 g)", price_usd=1.99,
               tags=["vegan", "crunchy snack", "14 g/serving"],
               url="https://example.com/affiliate-placeholder/roasted-edamame"),
]

_DISCLOSURE = (
    "Heads up: product links may be affiliate links — if you buy through them we "
    "may earn a commission (typically 3-8%) at no extra cost to you. Links below "
    "are placeholders until partnerships are live. We only list products we'd "
    "recommend to GLP-1 users regardless of commission."
)


@router.get("/marketplace", response_model=MarketplaceOut)
async def marketplace(user: User = Depends(get_current_user)):
    return MarketplaceOut(items=_MARKETPLACE, disclosure=_DISCLOSURE)
