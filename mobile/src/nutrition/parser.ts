/**
 * Neutron voice-log: dictated-transcript parser + protein estimator.
 *
 * "I had 250 grams of grilled chicken breast with some rice and a protein
 * shake" ->
 *   [ {qty 250, unit g, "grilled chicken breast"},
 *     {qty null, "rice"},
 *     {qty 1, unit count, "protein shake"} ]
 * then each item is resolved through the cache-first tiers in matcher.ts and
 * priced in grams of protein. Practical/approximate by design.
 *
 * Pure TS — no React Native imports (unit-testable under node).
 */

import { Food } from "./foods";
import { classifyCategory, FoodMatch, matchFood, normalize } from "./matcher";

// ------------------------------------------------------------ quantities

const NUMBER_WORDS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8,
  nine: 9, ten: 10, eleven: 11, twelve: 12, dozen: 12, half: 0.5,
  quarter: 0.25, couple: 2, few: 3, single: 1, an: 1, a: 1,
};

interface UnitDef { grams: number | "serving" | "cup"; aliases: string[] }

/** grams: fixed weight | "serving" = multiples of the food's default serving
 * | "cup" = volume, resolved per food category. */
const UNITS: Record<string, UnitDef> = {
  g: { grams: 1, aliases: ["g", "gram", "grams", "gr"] },
  kg: { grams: 1000, aliases: ["kg", "kilo", "kilos", "kilogram", "kilograms"] },
  oz: { grams: 28.35, aliases: ["oz", "ounce", "ounces"] },
  lb: { grams: 453.6, aliases: ["lb", "lbs", "pound", "pounds"] },
  ml: { grams: 1, aliases: ["ml", "milliliter", "milliliters", "millilitre", "millilitres"] },
  cup: { grams: "cup", aliases: ["cup", "cups"] },
  tbsp: { grams: 15, aliases: ["tbsp", "tablespoon", "tablespoons"] },
  tsp: { grams: 5, aliases: ["tsp", "teaspoon", "teaspoons"] },
  serving: {
    grams: "serving",
    aliases: [
      "serving", "servings", "piece", "pieces", "slice", "slices", "scoop",
      "scoops", "can", "cans", "bottle", "bottles", "glass", "glasses",
      "bowl", "bowls", "plate", "plates", "order", "portion", "portions",
      "bar", "bars", "tub", "tubs", "container", "pack", "packet", "handful",
      "fillet", "fillets", "patty", "patties", "link", "links", "stick",
      "sticks", "egg", "eggs",
    ],
  },
};

const UNIT_LOOKUP = new Map<string, keyof typeof UNITS>();
(Object.keys(UNITS) as (keyof typeof UNITS)[]).forEach((k) =>
  UNITS[k].aliases.forEach((a) => UNIT_LOOKUP.set(a, k)),
);

/** Volume units vary with what's in the cup — coarse per-food densities. */
function cupGrams(food: Food | null): number {
  if (!food) return 200;
  switch (food.category) {
    case "beverages": case "dairy": case "supplements": return 240;
    case "grains": case "legumes": case "prepared": return 180;
    case "vegetables": case "fruits": return 130;
    case "nuts_seeds": case "snacks": return 110;
    default: return 150;
  }
}

// ---------------------------------------------------------- segmentation

const FILLER_PREFIXES = [
  "i had", "i ate", "i just had", "i just ate", "i have eaten", "i've had",
  "i drank", "i just drank", "i also had", "i also ate", "just had", "had",
  "ate", "for breakfast", "for lunch", "for dinner", "for a snack",
  "this morning", "this afternoon", "this evening", "tonight", "today",
  "log", "add", "please log", "please add", "i think", "about", "around",
  "roughly", "approximately", "maybe", "like", "then", "also", "and then",
];

const CONNECTOR_SPLIT =
  /,|\band\b|\bwith\b|\bplus\b|\balong with\b|\bas well as\b|\btogether with\b|\bfollowed by\b/g;

/** Foods whose names contain a connector word — protect them before the
 * split so "mac and cheese" doesn't become "mac" + "cheese". */
const PROTECTED = [
  "mac and cheese", "macaroni and cheese", "fish and chips", "pb and j",
  "peanut butter and jelly", "biscuits and gravy", "steak and eggs",
  "bacon egg and cheese", "sweet and sour chicken", "spaghetti with meatballs",
  "pasta with meat sauce", "oatmeal with protein powder", "yogurt with granola",
  "avocado toast with egg", "bagel with cream cheese", "salad with chicken",
  "curry with rice", "butter chicken with rice", "corn on the cob",
];

/** Like normalize() but KEEPS commas — they're segment boundaries and must
 * survive until the split (normalize() would erase them). */
function segNormalize(raw: string): string {
  return raw
    .normalize("NFKD")
    // eslint-disable-next-line no-control-regex
    .replace(/[^\x00-\x7F]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9%./, ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Split a dictated transcript into per-food segments (protecting compound
 * food names) and strip conversational filler from each. */
export function segmentTranscript(transcript: string): string[] {
  let text = ` ${segNormalize(transcript)} `;
  // Marker must survive normalize(): lowercase letters/digits only.
  PROTECTED.forEach((p, i) => {
    text = text.split(` ${p} `).join(` qqfood${i}qq `);
  });
  // Strip leading filler repeatedly ("ok so for lunch i had ...").
  const segments = text
    .split(CONNECTOR_SPLIT)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      let out = s;
      let changed = true;
      while (changed) {
        changed = false;
        for (const f of FILLER_PREFIXES) {
          if (out === f) { out = ""; changed = false; break; }
          if (out.startsWith(f + " ")) { out = out.slice(f.length + 1); changed = true; }
        }
      }
      return out.trim();
    })
    .filter((s) => s.length > 1)
    .map((s) => {
      PROTECTED.forEach((p, i) => {
        s = s.split(`qqfood${i}qq`).join(p);
      });
      return s;
    });
  return segments;
}

// ------------------------------------------------------- quantity parsing

export interface ParsedSegment {
  rawPhrase: string;    // segment as dictated (post-normalize)
  foodPhrase: string;   // segment minus quantity/unit words
  quantity: number | null;
  unit: keyof typeof UNITS | null;
}

const QTY_RE = /^([0-9]+(?:[.,][0-9]+)?|[0-9]+\s*\/\s*[0-9]+)\s*/;

/** Extract quantity + unit from one segment, leaving the bare food phrase. */
export function parseSegment(segment: string): ParsedSegment {
  let rest = segment.trim();
  let quantity: number | null = null;
  let unit: keyof typeof UNITS | null = null;

  // Numeric quantity: "250 grams of", "1.5 cups", "1/2 cup"
  const m = rest.match(QTY_RE);
  if (m) {
    const raw = m[1].replace(",", ".");
    quantity = raw.includes("/")
      ? (() => { const [a, b] = raw.split("/").map((x) => parseFloat(x)); return b ? a / b : null; })()
      : parseFloat(raw);
    rest = rest.slice(m[0].length);
  } else {
    // Word quantity: "two eggs", "half a cup of", "a couple of slices"
    const words = rest.split(" ");
    if (words.length > 1 && NUMBER_WORDS[words[0]] !== undefined) {
      quantity = NUMBER_WORDS[words[0]];
      rest = words.slice(1).join(" ");
      // "half a cup", "a couple of" — swallow the article
      if (rest.startsWith("a ") || rest.startsWith("an ")) rest = rest.replace(/^an? /, "");
    }
  }

  // Unit directly after the quantity: "250 grams of chicken"
  const words = rest.split(" ").filter(Boolean);
  if (words.length > 1 && UNIT_LOOKUP.has(words[0])) {
    unit = UNIT_LOOKUP.get(words[0])!;
    rest = words.slice(1).join(" ");
    if (rest.startsWith("of ")) rest = rest.slice(3);
  } else if (quantity !== null && words.length > 0) {
    // Trailing count unit: "two eggs", "three slices" already consumed above;
    // here handle "chicken breast 200 grams" style (unit at the end).
    const last = words[words.length - 1];
    if (UNIT_LOOKUP.has(last) && words.length > 1) {
      unit = UNIT_LOOKUP.get(last)!;
      rest = words.slice(0, -1).join(" ");
    }
  }

  // Bare count with a countable food ("two eggs" -> unit=serving via "eggs"
  // being both food and unit-alias is avoided: only treat as serving count)
  if (quantity !== null && unit === null) unit = "serving";

  return { rawPhrase: segment, foodPhrase: rest.trim() || segment, quantity, unit };
}

// ------------------------------------------------------------ estimation

export type ResolutionTier = "cache" | "exact" | "fuzzy" | "classifier" | "ai";

export interface DraftItem {
  id: string;             // local uuid for list editing
  rawPhrase: string;
  foodPhrase: string;     // quantity-stripped phrase — cache key + AI payload
  name: string;           // display/canonical name (editable)
  portionG: number;       // estimated grams of food (editable)
  portionLabel: string;   // human portion description
  proteinPer100g: number;
  proteinG: number;       // the number that gets logged (editable)
  tier: ResolutionTier;
  confidence: number;     // 0..1 — drives the "approx, tap to fix" badge
  needsAi: boolean;       // true => phrase should go to /nutrition/parse
}

export interface CachedEstimate {
  name: string;
  proteinPer100g: number;
  portionEstG: number;
  source: "correction" | "ai";
}

let _seq = 0;
function localId(): string {
  _seq += 1;
  return `d${Date.now().toString(36)}${_seq}`;
}

/** Convert a parsed quantity/unit into grams + a human-readable portion label. */
function portionGrams(seg: ParsedSegment, food: Food | null,
                      fallbackServingG: number): { grams: number; label: string } {
  const qty = seg.quantity ?? 1;
  const servingG = food?.defaultServingG ?? fallbackServingG;
  const servingLabel = food?.servingLabel ?? "serving";
  if (seg.unit === null || seg.unit === "serving") {
    const grams = qty * servingG;
    const label = seg.quantity === null ? servingLabel : `${qty} × ${servingLabel}`;
    return { grams, label };
  }
  if (seg.unit === "cup") return { grams: qty * cupGrams(food), label: `${qty} cup${qty === 1 ? "" : "s"}` };
  const def = UNITS[seg.unit].grams as number;
  return { grams: qty * def, label: `${qty} ${seg.unit}` };
}

function round1(x: number): number { return Math.round(x * 10) / 10; }

/**
 * Resolve one parsed segment through the LOCAL tiers (1-4). Tier 5 (AI) is
 * signalled via needsAi — the screen batches those into one /nutrition/parse
 * call, and only when online. `cacheLookup` is the device alias cache
 * (corrections + past AI answers) keyed by normalize(foodPhrase).
 */
export function resolveSegment(
  seg: ParsedSegment,
  cacheLookup: (phraseNorm: string) => CachedEstimate | null,
): DraftItem {
  const norm = normalize(seg.foodPhrase);

  // Tier 1: alias cache — user corrections and previous AI answers win.
  const cached = cacheLookup(norm);
  if (cached) {
    const { grams, label } = portionGrams(seg, null, cached.portionEstG);
    return {
      id: localId(), rawPhrase: seg.rawPhrase, foodPhrase: seg.foodPhrase, name: cached.name,
      portionG: round1(grams), portionLabel: label,
      proteinPer100g: cached.proteinPer100g,
      proteinG: round1((cached.proteinPer100g * grams) / 100),
      tier: "cache", confidence: cached.source === "correction" ? 0.95 : 0.8,
      needsAi: false,
    };
  }

  // Tiers 2+3: bundled DB.
  const match: FoodMatch | null = matchFood(seg.foodPhrase);
  if (match) {
    const { grams, label } = portionGrams(seg, match.food, match.food.defaultServingG);
    return {
      id: localId(), rawPhrase: seg.rawPhrase, foodPhrase: seg.foodPhrase, name: match.food.name,
      portionG: round1(grams), portionLabel: label,
      proteinPer100g: match.food.proteinPer100g,
      proteinG: round1((match.food.proteinPer100g * grams) / 100),
      tier: match.score === 1 ? "exact" : "fuzzy",
      confidence: match.score, needsAi: match.score < 0.75,
    };
  }

  // Tier 4: on-device classifier — usable offline estimate, flags for AI.
  const guess = classifyCategory(seg.foodPhrase);
  const { grams, label } = portionGrams(seg, null, guess.defaultServingG);
  return {
    id: localId(), rawPhrase: seg.rawPhrase, foodPhrase: seg.foodPhrase, name: seg.foodPhrase,
    portionG: round1(grams), portionLabel: label,
    proteinPer100g: guess.proteinPer100g,
    proteinG: round1((guess.proteinPer100g * grams) / 100),
    tier: "classifier", confidence: Math.min(0.5, guess.confidence),
    needsAi: true,
  };
}

/** Full pipeline: transcript -> draft items (local tiers only). */
export function parseTranscript(
  transcript: string,
  cacheLookup: (phraseNorm: string) => CachedEstimate | null,
): DraftItem[] {
  return segmentTranscript(transcript)
    .map(parseSegment)
    .filter((s) => s.foodPhrase.length > 1)
    .map((s) => resolveSegment(s, cacheLookup));
}
