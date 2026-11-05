// API client with transparent access-token refresh (spec F4).
// On a 401, try one silent refresh, then retry the original request once.
import { API_BASE_URL } from "./config";
import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from "./tokenStore";

type Json = Record<string, unknown>;

/** Low-level fetch: prefixes the API base URL and attaches the bearer token. */
async function rawFetch(path: string, init: RequestInit, withAuth: boolean): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (withAuth) {
    const access = await getAccessToken();
    if (access) headers["Authorization"] = `Bearer ${access}`;
  }
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

/** Exchange the stored refresh token for a new pair; clears tokens on failure. */
async function tryRefresh(): Promise<boolean> {
  const refresh = await getRefreshToken();
  if (!refresh) return false;
  const res = await rawFetch(
    "/auth/refresh",
    { method: "POST", body: JSON.stringify({ refresh_token: refresh }) },
    false,
  );
  if (!res.ok) {
    await clearTokens();
    return false;
  }
  const data = (await res.json()) as { access_token: string; refresh_token: string };
  await saveTokens(data.access_token, data.refresh_token);
  return true;
}

// --- Paywall interception (HTTP 402) ---
// Every metered endpoint answers 402 with a flat, machine-readable body:
//   {"error":"quota_exhausted","kind":"equipment_scan","paywall":"steel_equipment_pack_5"}
// Handling that centrally (here) rather than per-screen means a screen only
// has to catch the error to stop its own spinner — routing to the paywall has
// already happened, and any endpoint metered LATER is covered for free.

/** Thrown for any 402. `paywall` names the product the paywall should present. */
export class QuotaError extends Error {
  readonly status = 402;
  constructor(readonly kind: string, readonly paywall: string) {
    super("You've used up this feature's included scans.");
    this.name = "QuotaError";
  }
}

type PaywallHandler = (error: QuotaError) => void;
let paywallHandler: PaywallHandler | null = null;

/** Register the app-level paywall router (BillingContext does this on mount).
 *  Returns an unsubscribe so a remount can't leave a stale handler behind. */
export function setPaywallHandler(handler: PaywallHandler | null): () => void {
  paywallHandler = handler;
  return () => {
    if (paywallHandler === handler) paywallHandler = null;
  };
}

/** Turn a 402 body into a QuotaError, notify the app, and throw. */
function raiseQuota(body: unknown): never {
  const b = (body ?? {}) as { kind?: string; paywall?: string };
  const err = new QuotaError(b.kind ?? "unknown", b.paywall ?? "steel_starter_unlock");
  try {
    paywallHandler?.(err);
  } catch {
    // A failing paywall handler must not mask the original error.
  }
  throw err;
}

/**
 * JSON API call with transparent auth: on a 401 it refreshes once and retries.
 * Throws QuotaError on 402 (after routing to the paywall), Error(detail) on any
 * other non-2xx response.
 */
export async function apiFetch<T = Json>(
  path: string,
  init: RequestInit = {},
  withAuth = true,
): Promise<T> {
  let res = await rawFetch(path, init, withAuth);
  if (res.status === 401 && withAuth) {
    const refreshed = await tryRefresh();
    if (refreshed) res = await rawFetch(path, init, withAuth);
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.status === 402) raiseQuota(body);
  if (!res.ok) {
    const detail = (body as { detail?: string } | null)?.detail ?? `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return body as T;
}

// --- Typed endpoint helpers ---
export const AuthApi = {
  requestOtp: (email: string, phone?: string) =>
    apiFetch<{ message: string }>(
      "/auth/request-otp",
      { method: "POST", body: JSON.stringify({ email, phone }) },
      false,
    ),
  verifyOtp: async (email: string, code: string) => {
    const t = await apiFetch<{ access_token: string; refresh_token: string }>(
      "/auth/verify-otp",
      { method: "POST", body: JSON.stringify({ email, code }) },
      false,
    );
    await saveTokens(t.access_token, t.refresh_token);
    return t;
  },
  logout: async () => {
    const refresh = await getRefreshToken();
    try {
      await apiFetch("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }, false);
    } finally {
      await clearTokens();
    }
  },
};

/** Account deletion (App Store Review Guideline 5.1.1(v)). */
export const AccountApi = {
  /** Start deletion. The server signs every device out, so the caller must
   *  clear local tokens straight after and drop back to the sign-in screen. */
  requestDeletion: async () => {
    const res = await apiFetch<DeletionStatus>("/me/deletion", { method: "POST" });
    await clearTokens();
    return res;
  },
  /** Cancel a pending deletion and keep the account. */
  cancelDeletion: () => apiFetch<DeletionStatus>("/me/deletion", { method: "DELETE" }),
};

// Couch-to-Weights beginner ramp state, carried on /me (null unless beginner).
export type CouchState = {
  mode: boolean;
  week: number;
  unlocked: number;
  full: number;
  graduated: boolean;
  decision_due: boolean;
  nudge_level: number;
};

export type Habits = {
  days_per_week: number;
  session_minutes: number;
  experience: string;
  onboarded: boolean;
  couch?: CouchState | null;
};

export type Me = {
  id: string;
  email: string;
  email_verified: boolean;
  training_mode: string;
  name?: string | null;
  habits: Habits | null;
  /** Set while the account is in the deletion grace window (App Store 5.1.1(v)).
   *  Both are absent on older backends, so treat undefined as "active". */
  deletion_requested_at?: string | null;
  deletion_scheduled_for?: string | null;
};

export type DeletionStatus = {
  pending: boolean;
  deletion_scheduled_for: string | null;
  grace_period_days: number;
  message: string;
};

export type HabitsInput = {
  days_per_week: number;
  session_minutes: number;
  experience: string;
  name?: string | null;
};

export const UserApi = {
  me: () => apiFetch<Me>("/me"),
  habitsDefaults: () => apiFetch<Habits>("/habits/defaults", {}, false),
  setHabits: (h: HabitsInput) =>
    apiFetch<Habits>("/habits", { method: "PUT", body: JSON.stringify(h) }),
};

// --- Inventory (Increment 2) ---
export type EquipmentItem = {
  id?: string;
  type: string;
  quantity: number;
  load_min: number | null;
  load_max: number | null;
  load_increment: number | null;
  attributes: Record<string, unknown>;
  confidence?: number | null;
  confirmed?: boolean;
};

export type InventoryVersion = {
  id: string;
  version_no: number;
  status: string;
  source: string;
  items: EquipmentItem[];
};

export type PhotoAsset = { uri: string; mimeType?: string | null };

// Multipart upload needs the auth header + one silent refresh, but NOT a JSON
// content-type (fetch must set the multipart boundary itself).
async function authedMultipart(path: string, form: FormData): Promise<InventoryVersion> {
  const doSend = async () => {
    const access = await getAccessToken();
    return fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: access ? { Authorization: `Bearer ${access}` } : {},
      body: form,
    });
  };
  let res = await doSend();
  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) res = await doSend();
  }
  const body = await res.json().catch(() => null);
  if (res.status === 402) raiseQuota(body);  // equipment scan quota
  if (!res.ok) throw new Error((body as { detail?: string } | null)?.detail ?? `Upload failed (${res.status})`);
  return body as InventoryVersion;
}

export const InventoryApi = {
  // mode "replace" = full rescan (default); "add" = merge into current inventory.
  capture: (photos: PhotoAsset[], consentToTrain: boolean, mode: "replace" | "add" = "replace") => {
    const form = new FormData();
    photos.forEach((p, idx) => {
      // RN FormData file shape
      form.append("images", {
        uri: p.uri,
        name: `capture_${idx}.jpg`,
        type: p.mimeType ?? "image/jpeg",
      } as unknown as Blob);
    });
    form.append("consent_to_train", consentToTrain ? "true" : "false");
    form.append("mode", mode);
    return authedMultipart("/inventory/capture", form);
  },
  confirm: (versionId: string, items: EquipmentItem[]) =>
    apiFetch<InventoryVersion>(`/inventory/${versionId}/confirm`, {
      method: "PUT",
      body: JSON.stringify({ items: items.map(stripItem) }),
    }),
  current: () => apiFetch<InventoryVersion | null>("/inventory"),
  edit: (items: EquipmentItem[]) =>
    apiFetch<InventoryVersion>("/inventory/edit", {
      method: "POST",
      body: JSON.stringify({ items: items.map(stripItem) }),
    }),
};

// --- Programs (Increment 3) ---
export type ProgramExercise = {
  name: string;
  pattern: string;
  primary: string[];
  sets: number;
  reps: string;
  rir: string;
  compound: boolean;
  substituted_from: string | null;
  description: string;
  video_url: string;
  rest_seconds: number;
  added_by_user?: boolean;
};
export type ProgramDay = {
  name: string;
  exercises: ProgramExercise[];
  gaps: string[];
  est_minutes: number;
};
export type Program = {
  id: string;
  days_per_week: number;
  session_minutes: number;
  experience: string;
  inventory_version_id: string | null;
  stale: boolean;
  created_at: string;
  days: ProgramDay[];
  weekly_volume: Record<string, number>;
  notes: string[];
  gaps: string[];
};

export type GenerateOpts = {
  daysPerWeek?: number;
  bodyweightOnly?: boolean;
  equipmentTypes?: string[] | null;
};

// Session-lived cache for the static exercise library (see exerciseLibrary()).
let exerciseLibraryCache: Promise<ExerciseLibraryItem[]> | null = null;

export const ProgramApi = {
  generate: (opts: GenerateOpts = {}) =>
    apiFetch<Program>("/programs/generate", {
      method: "POST",
      body: JSON.stringify({
        days_per_week: opts.daysPerWeek ?? null,
        bodyweight_only: opts.bodyweightOnly ?? null,
        equipment_types: opts.equipmentTypes ?? null,
      }),
    }),
  current: () => apiFetch<Program | null>("/programs/current"),

  // --- Add-your-own-exercise (library pick + social-media suggestion) ---
  // The library is static server-side data, so fetch it once per app session and
  // reuse it — no need to re-hit the network every time the picker opens.
  exerciseLibrary: () => {
    if (!exerciseLibraryCache) {
      exerciseLibraryCache = apiFetch<ExerciseLibraryItem[]>("/programs/exercise-library")
        .catch((e) => {
          exerciseLibraryCache = null; // let the next open retry after a failure
          throw e;
        });
    }
    return exerciseLibraryCache;
  },
  classifyExercise: (text: string) =>
    apiFetch<ClassifiedExercise>("/programs/exercises/classify", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  addExercise: (payload: AddExercisePayload) =>
    apiFetch<Program>("/programs/exercises/add", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  removeExercise: (dayIndex: number, name: string) =>
    apiFetch<Program>("/programs/exercises/remove", {
      method: "POST",
      body: JSON.stringify({ day_index: dayIndex, name }),
    }),
};

export type ExerciseLibraryItem = {
  id: string;
  name: string;
  pattern: string;
  primary: string[];
  compound: boolean;
};

export type ClassifiedExercise = {
  name: string;
  primary: string[];
  compound: boolean;
  description: string;
  confidence: number;
  source: string; // library | ai | stub | bedrock:...
  suggested_day_index: number;
  suggested_day_name: string;
};

export type AddExercisePayload = {
  library_id?: string;
  name?: string;
  primary?: string[];
  compound?: boolean;
  description?: string;
  sets?: number;
  day_index?: number;
};

// --- Couch-to-Weights (beginner progressive onboarding) ---
export type CouchView = {
  mode: boolean;
  week: number;
  unlocked: number;
  full: number;
  graduated: boolean;
  decision_due: boolean;
  nudge_level: number;
  headline: string;
  message: string;
  added_today: string | null;
  added_reason: string | null;
  days: ProgramDay[];
};

export const CouchApi = {
  get: () => apiFetch<CouchView>("/programs/couch"),
  advance: (action: "add" | "skip") =>
    apiFetch<CouchView>("/programs/couch/advance", {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  restart: () => apiFetch<{ message: string }>("/programs/couch/restart", { method: "POST" }),
  graduate: () => apiFetch<{ message: string }>("/programs/couch/graduate", { method: "POST" }),
};

// --- Workouts (Increment 4) ---
export type SetLog = {
  id: string;
  exercise_name: string;
  set_number: number;
  reps: number;
  rir: number;
  weight: number | null;
};
export type ProgressionSuggestion = { exercise_name: string; action: string; message: string };
export type WorkoutSession = {
  id: string;
  program_id: string | null;
  day_index: number;
  day_name: string;
  readiness: number | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  sets: SetLog[];
  suggestions: ProgressionSuggestion[];
};

export type WorkoutHistoryItem = {
  id: string;
  day_name: string;
  status: string;
  started_at: string;
  set_count: number;
  /** Which program day this session was. Added to `/workouts/history` after the
   *  shipped backend, so treat it as absent on older servers and fall back to
   *  matching `day_name` (see `programDays.ts`). */
  day_index?: number;
};

export const WorkoutApi = {
  history: () => apiFetch<WorkoutHistoryItem[]>("/workouts/history"),
  start: (dayIndex: number, readiness?: number, programId?: string) =>
    apiFetch<WorkoutSession>("/workouts/start", {
      method: "POST",
      body: JSON.stringify({ day_index: dayIndex, readiness: readiness ?? null, program_id: programId ?? null }),
    }),
  logSet: (sessionId: string, set: {
    exercise_name: string; set_number: number; reps: number; rir: number; weight: number | null; reps_range: string;
  }) =>
    apiFetch<WorkoutSession>(`/workouts/${sessionId}/log`, { method: "POST", body: JSON.stringify(set) }),
  finish: (sessionId: string) =>
    apiFetch<WorkoutSession>(`/workouts/${sessionId}/finish`, { method: "POST" }),
  lastPerformance: () =>
    apiFetch<Record<string, { weight: number | null; reps: number; rir: number }>>("/workouts/last-performance"),
  get: (sessionId: string) => apiFetch<WorkoutSession>(`/workouts/${sessionId}`),
};

/** Drop client-only fields (id, confidence, confirmed) before submitting items. */
function stripItem(i: EquipmentItem) {
  return {
    type: i.type,
    quantity: i.quantity,
    load_min: i.load_min,
    load_max: i.load_max,
    load_increment: i.load_increment,
    attributes: i.attributes ?? {},
  };
}

// --- Analytics (Reporting & Analytics v1) ---
// All aggregation is server-side; `tz` = minutes east of UTC so buckets land
// in the user's local day/week/month.
/** Device timezone offset in minutes east of UTC (what the API expects). */
function tzMinutes(): number {
  return -new Date().getTimezoneOffset();
}

export type AnalyticsRange = "30d" | "90d" | "6m" | "1y" | "all";

export type WeekCount = { week_start: string; count: number };
export type Consistency = {
  target_per_week: number;
  this_week: number;
  streak_weeks: number;
  weeks: WeekCount[];
};
export type VolumeSummary = { this_month: number; last_month: number; pct_change: number | null };
export type PrHighlight = { exercise: string; kind: string; value: number; previous: number; date: string };
export type ImprovedItem = { exercise: string; pct: number; sessions: number };
export type MuscleShare = { muscle: string; volume: number; share: number };
export type AnalyticsSummary = {
  consistency: Consistency;
  volume: VolumeSummary;
  recent_prs: PrHighlight[];
  most_improved: ImprovedItem[];
  muscle_focus: MuscleShare[];
};

export type ExerciseListItem = { name: string; muscles: string[]; sessions: number; last_performed: string };
export type ChartPoint = { date: string; value: number };
export type BestSet = { date: string; weight: number; reps: number };
export type ExerciseDetail = {
  exercise: string;
  range: AnalyticsRange;
  unloaded: boolean;
  e1rm_series: ChartPoint[];
  volume_weekly: ChartPoint[];
  best_sets: BestSet[];
  reps_series: ChartPoint[];
  pct_change: number | null;
  prs: { e1rm: ChartPoint | null; weight: BestSet | null };
  plateau: boolean;
  plateau_message: string | null;
  projection: { target: number; date: string } | null;
};

export type HeatmapDay = { date: string; sets: number; volume: number };
export type HistorySession = {
  id: string;
  date: string;
  day_name: string;
  set_count: number;
  volume: number;
  exercises: string[];
  muscles: string[];
};
export type AnalyticsHistory = { days: HeatmapDay[]; sessions: HistorySession[] };

// --- Neutron nutrition module (Increment 5) ---
export type NutritionProfile = {
  current_weight_kg: number | null;
  goal_weight_kg: number | null;
  protein_target_g: number | null;
  target_mode: string; // auto | custom
  protein_multiplier: number; // auto-mode g protein per kg bodyweight (2.2 ≈ 1 g/lb)
  diet_pattern: string; // omnivore | vegetarian | pescatarian | vegan
  restrictions: string[];
  onboarded: boolean;
};

export type ScannedFoodItem = {
  name: string;
  quantity: string;
  category: string; // pantry | fridge | freezer | other
  protein_per_100g: number | null;
  protein_density: string; // high | medium | low
  confidence: number;
};

export type PantryItemT = {
  id?: string;
  name: string;
  quantity: string;
  category: string;
  protein_per_100g: number | null;
  protein_density: string;
  source: string; // scan | manual
  confidence: number | null;
};

export type RecipeIngredient = { name: string; quantity: string; from_pantry: boolean };
export type Recipe = {
  title: string;
  description: string;
  servings: number;
  prep_minutes: number;
  cook_minutes: number;
  difficulty: string;
  protein_g: number; // per serving
  calories: number;
  carbs_g: number;
  fat_g: number;
  ingredients: RecipeIngredient[];
  steps: string[];
  tags: string[];
  is_vegan: boolean;
  is_vegetarian: boolean;
};
export type RecipesOut = { recipes: Recipe[]; generator: string; newly_earned_badges: string[] };
export type DayPlanMeal = { slot: string; recipe: Recipe };
export type DayPlan = {
  meals: DayPlanMeal[];
  total_protein_g: number;
  total_calories: number;
  note: string;
  generator: string;
};
export type SavedRecipeT = {
  id: string;
  title: string;
  protein_g: number;
  calories: number;
  recipe: Recipe;
  source: string;
  created_at: string;
};

export type ProteinLogEntry = {
  id: string;
  grams: number;
  calories: number | null;
  label: string;
  source: string;
  logged_at: string;
};
export type LogResult = {
  entry: ProteinLogEntry;
  today_total_g: number;
  target_g: number | null;
  pct_of_target: number | null;
  newly_earned_badges: string[];
  message: string;
};
// Voice-log AI fallback (/nutrition/parse) — only reached for phrases the
// on-device matcher can't resolve; responses are cached on both ends.
export type ParsedFoodT = {
  phrase: string;
  name: string;
  protein_per_100g: number;
  portion_est_g: number;
  protein_g: number;
  confidence: number;
  cached: boolean;
};
export type ParseFoodsResult = { items: ParsedFoodT[]; parser: string };

export type DayBar = { date: string; grams: number; hit: boolean };
export type WeekAvg = { week_start: string; avg_grams: number };
export type NutritionBadgeT = {
  key: string;
  name: string;
  description: string;
  earned: boolean;
  awarded_at: string | null;
};
export type NutritionSummary = {
  target_g: number | null;
  today_g: number;
  today_pct: number | null;
  week_days: DayBar[];
  week_avg_g: number;
  trend_weeks: WeekAvg[];
  daily_streak: number;
  best_daily_streak: number;
  weekly_streak: number;
  total_hit_days: number;
  level: number;
  level_title: string;
  next_level_at: number | null;
  muscle_score: number;
  badges: NutritionBadgeT[];
  message: string;
};

export type MarketItem = {
  name: string;
  brand: string;
  category: string;
  protein_per_serving_g: number;
  serving: string;
  price_usd: number;
  tags: string[];
  url: string;
  url_is_placeholder: boolean;
};
export type Marketplace = { items: MarketItem[]; disclosure: string };

export type WeightEntry = { weight_kg: number; logged_at: string };

// Pantry scan is multipart like inventory capture, but returns a scan payload.
async function nutritionScanUpload(photos: PhotoAsset[]): Promise<{ items: ScannedFoodItem[]; recognizer: string }> {
  const form = new FormData();
  photos.forEach((p, idx) => {
    form.append("images", {
      uri: p.uri,
      name: `pantry_${idx}.jpg`,
      type: p.mimeType ?? "image/jpeg",
    } as unknown as Blob);
  });
  const doSend = async () => {
    const access = await getAccessToken();
    return fetch(`${API_BASE_URL}/nutrition/pantry/scan`, {
      method: "POST",
      headers: access ? { Authorization: `Bearer ${access}` } : {},
      body: form,
    });
  };
  let res = await doSend();
  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) res = await doSend();
  }
  const body = await res.json().catch(() => null);
  if (res.status === 402) raiseQuota(body);  // meal scan quota
  if (!res.ok) throw new Error((body as { detail?: string } | null)?.detail ?? `Scan failed (${res.status})`);
  return body as { items: ScannedFoodItem[]; recognizer: string };
}

export const NutritionApi = {
  profile: () => apiFetch<NutritionProfile>("/nutrition/profile"),
  saveProfile: (p: {
    current_weight_kg: number | null;
    goal_weight_kg: number | null;
    protein_target_g: number | null; // null = auto (multiplier × kg)
    protein_multiplier?: number | null; // g/kg; null keeps the saved value
    diet_pattern: string;
    restrictions: string[];
  }) => apiFetch<NutritionProfile>("/nutrition/profile", { method: "PUT", body: JSON.stringify(p) }),
  logWeight: (weightKg: number) =>
    apiFetch<NutritionProfile>("/nutrition/weight", { method: "POST", body: JSON.stringify({ weight_kg: weightKg }) }),
  weightHistory: (days = 180) => apiFetch<WeightEntry[]>(`/nutrition/weight?days=${days}`),

  scanPantry: (photos: PhotoAsset[]) => nutritionScanUpload(photos),
  pantry: () => apiFetch<PantryItemT[]>("/nutrition/pantry"),
  replacePantry: (items: Omit<PantryItemT, "id">[]) =>
    apiFetch<PantryItemT[]>("/nutrition/pantry", { method: "PUT", body: JSON.stringify({ items }) }),

  generateRecipes: (opts: {
    use_pantry?: boolean;
    count?: number;
    min_protein_per_serving?: number;
    diet_pattern?: string | null;
    extra_restrictions?: string[];
    note?: string;
  }) => apiFetch<RecipesOut>("/nutrition/recipes/generate", { method: "POST", body: JSON.stringify(opts) }),
  adaptRecipe: (recipe: Recipe, mode: "vegan" | "vegetarian") =>
    apiFetch<RecipesOut>("/nutrition/recipes/adapt", { method: "POST", body: JSON.stringify({ recipe, mode }) }),
  surpriseMe: () => apiFetch<DayPlan>("/nutrition/recipes/surprise", { method: "POST" }),
  savedRecipes: () => apiFetch<SavedRecipeT[]>("/nutrition/recipes/saved"),
  saveRecipe: (recipe: Recipe, source: string) =>
    apiFetch<SavedRecipeT>("/nutrition/recipes/saved", { method: "POST", body: JSON.stringify({ recipe, source }) }),
  deleteSaved: (id: string) => apiFetch(`/nutrition/recipes/saved/${id}`, { method: "DELETE" }),

  parseFoods: (phrases: string[]) =>
    apiFetch<ParseFoodsResult>("/nutrition/parse", {
      method: "POST",
      body: JSON.stringify({ phrases }),
    }),

  logProtein: (grams: number, label: string, source = "quick_add", calories?: number) =>
    apiFetch<LogResult>(`/nutrition/log?tz=${tzMinutes()}`, {
      method: "POST",
      body: JSON.stringify({ grams, label, source, calories: calories ?? null }),
    }),
  logHistory: (days = 7) => apiFetch<ProteinLogEntry[]>(`/nutrition/log?days=${days}`),
  deleteLog: (id: string) => apiFetch(`/nutrition/log/${id}`, { method: "DELETE" }),

  summary: () => apiFetch<NutritionSummary>(`/nutrition/summary?tz=${tzMinutes()}`),
  marketplace: () => apiFetch<Marketplace>("/nutrition/marketplace"),
};

// --- Gamification (XP / streaks / weekly challenge / achievements) ---
// All history-derived, computed server-side; reading the summary also awards
// any newly earned achievements (returned in `newly_earned`).
export type GamificationXp = {
  total: number;
  level: number;
  level_title: string;
  xp_into_level: number;
  level_span: number;
  per_workout: number;
  per_protein_day: number;
  per_full_week: number;
  per_protein_week: number;
};
export type GamificationWorkout = {
  sessions_this_week: number;
  target_per_week: number;
  week_pct: number;
  current_streak: number;
  longest_streak: number;
  total_sessions: number;
};
export type GamificationProtein = {
  target_g: number | null;
  today_g: number;
  today_pct: number | null;
  week_hit_days: number;
  week_avg_g: number;
  daily_streak: number;
  best_daily_streak: number;
};
export type WeekBadgeT = { week_start: string; completed: number; target: number; pct: number };
export type AchievementT = {
  key: string;
  name: string;
  description: string;
  earned: boolean;
  awarded_at: string | null;
};
export type GamificationSummary = {
  xp: GamificationXp;
  workout: GamificationWorkout;
  protein: GamificationProtein;
  weeks: WeekBadgeT[];
  achievements: AchievementT[];
  newly_earned: string[];
  message: string;
};

export const GamificationApi = {
  summary: () => apiFetch<GamificationSummary>(`/gamification/summary?tz=${tzMinutes()}`),
};

// --- Billing (StoreKit purchases via RevenueCat) ---
// The SERVER decides entitlements; this is the display copy of that decision.
// Never cache it as the source of truth — re-read after any purchase, and let
// the 402 interceptor above be the real enforcement.
export type BillingTier = "free" | "starter" | "pro";

export type BillingStatus = {
  tier: BillingTier;
  /** -1 means unlimited (an active `pro` subscription). */
  equipment_scans_remaining: number;
  meal_scans_remaining: number;
  program_gens_remaining: number;
  /** ISO8601 end of the starter window, or null when it isn't running. */
  trial_ends_at: string | null;
  trial_seconds_left: number;
  pro_expires_at: string | null;
  /** True when the user can't do the next equipment scan without buying. */
  paywall_required: boolean;
  /** RevenueCat App User ID — always the backend users.id, never the email. */
  app_user_id: string;
  /** role -> App Store product id, so product ids live server-side. */
  products: Record<string, string>;
  provider: string; // stub | revenuecat
};

export const BillingApi = {
  status: () => apiFetch<BillingStatus>("/billing/status"),
  /** Reconcile with the store right after a purchase — webhooks lag a few
   *  seconds and the user is waiting on the result. */
  sync: () => apiFetch<BillingStatus>("/billing/sync", { method: "POST" }),
};

export const AnalyticsApi = {
  summary: () => apiFetch<AnalyticsSummary>(`/analytics/summary?tz=${tzMinutes()}`),
  exercises: () => apiFetch<ExerciseListItem[]>(`/analytics/exercises?tz=${tzMinutes()}`),
  exerciseDetail: (name: string, range: AnalyticsRange) =>
    apiFetch<ExerciseDetail>(
      `/analytics/exercises/${encodeURIComponent(name)}?range=${range}&tz=${tzMinutes()}`,
    ),
  history: (range: AnalyticsRange, exercise?: string, muscle?: string) => {
    const q = new URLSearchParams({ range, tz: String(tzMinutes()) });
    if (exercise) q.set("exercise", exercise);
    if (muscle) q.set("muscle", muscle);
    return apiFetch<AnalyticsHistory>(`/analytics/history?${q.toString()}`);
  },
};
