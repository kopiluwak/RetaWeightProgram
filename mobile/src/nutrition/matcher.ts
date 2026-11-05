/**
 * Neutron voice-log: on-device food matching + lightweight inference.
 *
 * Cache-first, AI-last resolution order (the caller walks these tiers):
 *   1. alias cache (user corrections + previously fetched AI answers)
 *   2. exact name/alias hit in the bundled DB
 *   3. fuzzy match (character-bigram Dice + token overlap) in the bundled DB
 *   4. Naive Bayes category classifier -> category-default estimate
 *      (this is the on-device inference tier: trained at startup from the
 *      bundled dataset itself, ~1 ms per phrase, no ML runtime, no network)
 *   5. only then: POST /nutrition/parse (Bedrock, server+device cached)
 *
 * Pure TS — no React Native imports (unit-testable under node).
 */

import { CATEGORY_DEFAULTS, Food, FoodCategory, FOODS } from "./foods";

/** MUST stay in sync with normalize_phrase() in backend neutron_parse.py so
 * the device alias cache and the server parse cache agree on keys. */
export function normalize(raw: string): string {
  return raw
    .normalize("NFKD")
    // eslint-disable-next-line no-control-regex
    .replace(/[^\x00-\x7F]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9%./ ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);
}

const STOPWORDS = new Set([
  "a", "an", "the", "of", "some", "my", "little", "bit", "few", "fresh",
  "nice", "big", "small", "large", "medium", "plain", "regular", "leftover",
]);

/** Normalized content tokens (stopwords and single chars dropped). */
export function tokens(s: string): string[] {
  return normalize(s).split(" ").filter((t) => t.length > 1 && !STOPWORDS.has(t));
}

// ------------------------------------------------------------ fuzzy match

/** Character-bigram multiset (space-padded) for Dice similarity. */
function bigrams(s: string): Map<string, number> {
  const m = new Map<string, number>();
  const padded = ` ${s} `;
  for (let i = 0; i < padded.length - 1; i++) {
    const g = padded.slice(i, i + 2);
    m.set(g, (m.get(g) ?? 0) + 1);
  }
  return m;
}

/** Sørensen–Dice over character bigrams: tolerant of dictation slips
 * ("chicken brest") and inflections ("eggs" vs "egg"). */
export function diceSimilarity(a: string, b: string): number {
  if (!a || !b) return 0;
  if (a === b) return 1;
  const ga = bigrams(a);
  const gb = bigrams(b);
  let overlap = 0;
  let na = 0;
  let nb = 0;
  ga.forEach((c) => { na += c; });
  gb.forEach((c) => { nb += c; });
  ga.forEach((c, g) => { overlap += Math.min(c, gb.get(g) ?? 0); });
  return (2 * overlap) / (na + nb);
}

interface IndexEntry { key: string; keyTokens: string[]; food: Food }

let EXACT: Map<string, Food> | null = null;
let INDEX: IndexEntry[] | null = null;

/** Lazily build the exact-lookup map and fuzzy index over names + aliases. */
function buildIndex(): void {
  EXACT = new Map();
  INDEX = [];
  for (const food of FOODS) {
    for (const name of [food.name, ...food.aliases]) {
      const key = normalize(name);
      if (!key) continue;
      if (!EXACT.has(key)) EXACT.set(key, food);
      INDEX.push({ key, keyTokens: tokens(name), food });
    }
  }
}

export interface FoodMatch {
  food: Food;
  score: number;          // 0..1
  matchedName: string;    // which name/alias won
}

/** Tier 2 + 3: exact then fuzzy lookup in the bundled DB.
 * Threshold 0.62 chosen against the unit fixtures: catches dictation typos
 * and word-order swaps while refusing cross-food confusions. */
export function matchFood(phrase: string, threshold = 0.62): FoodMatch | null {
  if (!EXACT || !INDEX) buildIndex();
  const norm = normalize(phrase);
  if (!norm) return null;

  const exact = EXACT!.get(norm);
  if (exact) return { food: exact, score: 1, matchedName: norm };

  const phraseTokens = tokens(phrase);
  let best: FoodMatch | null = null;
  for (const entry of INDEX!) {
    let score = diceSimilarity(norm, entry.key);
    // Token-containment boost: "grilled chicken breast with herbs" should
    // still find "chicken breast" even though the strings differ a lot.
    if (entry.keyTokens.length > 0) {
      const contained = entry.keyTokens.filter((t) =>
        phraseTokens.some((p) => p === t || diceSimilarity(p, t) >= 0.8),
      ).length;
      const containment = contained / entry.keyTokens.length;
      if (containment === 1) score = Math.max(score, 0.75 + 0.2 * Math.min(1, entry.keyTokens.length / Math.max(1, phraseTokens.length)));
      else score = Math.max(score, 0.7 * containment * (0.5 + 0.5 * score));
    }
    if (score > (best?.score ?? 0)) best = { food: entry.food, score, matchedName: entry.key };
  }
  return best && best.score >= threshold ? best : null;
}

// ------------------------------------- tier 4: Naive Bayes category model

/** Multinomial Naive Bayes over name/alias tokens, trained from the bundled
 * dataset at first use (~1000 short strings — sub-millisecond on device).
 * Used ONLY when nothing matches: it buys a sane offline protein-density
 * estimate ("pan seared barramundi" -> seafood -> 22 g/100g) instead of a
 * blind guess, and it costs no model runtime, no weights file, no network. */
interface NBModel {
  categories: FoodCategory[];
  logPrior: Map<FoodCategory, number>;
  logLikelihood: Map<FoodCategory, Map<string, number>>;
  logUnseen: Map<FoodCategory, number>;
}

let NB: NBModel | null = null;

/** Train the classifier once from the bundled dataset (Laplace-smoothed). */
function trainNB(): NBModel {
  const docs = new Map<FoodCategory, string[]>();
  for (const f of FOODS) {
    const toks = [f.name, ...f.aliases].flatMap((n) => tokens(n));
    docs.set(f.category, [...(docs.get(f.category) ?? []), ...toks]);
  }
  const vocab = new Set<string>();
  docs.forEach((ts) => ts.forEach((t) => vocab.add(t)));
  const V = vocab.size;

  const categories = [...docs.keys()];
  const logPrior = new Map<FoodCategory, number>();
  const logLikelihood = new Map<FoodCategory, Map<string, number>>();
  const logUnseen = new Map<FoodCategory, number>();
  const totalDocs = FOODS.length;

  for (const cat of categories) {
    const ts = docs.get(cat)!;
    const nDocs = FOODS.filter((f) => f.category === cat).length;
    logPrior.set(cat, Math.log(nDocs / totalDocs));
    const counts = new Map<string, number>();
    ts.forEach((t) => counts.set(t, (counts.get(t) ?? 0) + 1));
    const denom = ts.length + V; // Laplace smoothing
    const ll = new Map<string, number>();
    counts.forEach((c, t) => ll.set(t, Math.log((c + 1) / denom)));
    logLikelihood.set(cat, ll);
    logUnseen.set(cat, Math.log(1 / denom));
  }
  return { categories, logPrior, logLikelihood, logUnseen };
}

export interface CategoryGuess {
  category: FoodCategory;
  proteinPer100g: number;
  defaultServingG: number;
  confidence: number; // normalized posterior, 0..1
}

/** Tier 4: best-guess food category + its conservative default estimates. */
export function classifyCategory(phrase: string): CategoryGuess {
  if (!NB) NB = trainNB();
  const ts = tokens(phrase);
  const scores = NB.categories.map((cat) => {
    let s = NB!.logPrior.get(cat)!;
    const ll = NB!.logLikelihood.get(cat)!;
    const unseen = NB!.logUnseen.get(cat)!;
    for (const t of ts) s += ll.get(t) ?? unseen;
    return { cat, s };
  });
  scores.sort((a, b) => b.s - a.s);
  const top = scores[0];
  // Softmax-normalize the top score for a rough confidence signal.
  const maxS = top.s;
  const z = scores.reduce((acc, x) => acc + Math.exp(x.s - maxS), 0);
  const conf = 1 / z;
  const [ppg, serving] = CATEGORY_DEFAULTS[top.cat];
  return { category: top.cat, proteinPer100g: ppg, defaultServingG: serving, confidence: conf };
}
