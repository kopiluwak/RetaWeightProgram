// Billing/entitlement state for the app.
//
// Two hard rules, both from the spec and both worth restating where the code
// lives:
//
//   1. THE SERVER DECIDES, THE CLIENT DISPLAYS. Nothing here is the source of
//      truth for what the user has paid for. `status` is a cached copy of
//      GET /billing/status, refreshed after every purchase, and the real
//      enforcement is the 402 every metered endpoint returns. Do not gate a
//      feature on RevenueCat's CustomerInfo — that is the device's opinion.
//   2. The RevenueCat App User ID is the backend `users.id` UUID, never the
//      email. App User IDs travel in SDK payloads and webhooks; an email
//      there is a privacy leak, and it also breaks the moment a user changes
//      their address.
//
// The SDK is a NATIVE dependency (`react-native-purchases`). It needs
// `npm install` AND a full `npx expo run:ios` — a JS reload will not link it.
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Platform } from "react-native";
import Purchases, { LOG_LEVEL, PurchasesStoreProduct } from "react-native-purchases";
import { BillingApi, BillingStatus, QuotaError, setPaywallHandler } from "./api";
import { useAuth } from "./AuthContext";

/**
 * WHERE THE PAYWALL APPEARS. Single constant so the gate can be moved in one
 * edit (spec: gate at first scan, NOT at signup — the user finishes onboarding
 * and sees a real program before being asked for money).
 *
 * `"capture"` = the equipment-scan screen. Change to `"program"`, `"nutrition"`
 * or `"onboarding"` to move the gate earlier; `"never"` disables the proactive
 * gate entirely and leaves only the reactive 402 interception, which always
 * applies regardless of this value.
 */
export const PAYWALL_GATE: PaywallGate = "capture";

export type PaywallGate = "capture" | "program" | "nutrition" | "onboarding" | "never";

/** True when `screen` is the gate point and the server says payment is due. */
export function shouldGate(screen: string, status: BillingStatus | null): boolean {
  if (PAYWALL_GATE === "never" || !status) return false;
  return screen === PAYWALL_GATE && status.paywall_required;
}

/**
 * Public RevenueCat SDK key (iOS). Safe to ship — it is the *public* key, not
 * the secret one the backend uses. Empty string = SDK disabled: the app still
 * reads entitlements from our server and still intercepts 402s, it just can't
 * open a purchase sheet. That is the correct behaviour for a dev build or a
 * TestFlight build made before the RevenueCat project exists.
 *
 * TODO(launch): paste the iOS public SDK key from RevenueCat -> Project
 * settings -> API keys -> Apple App Store (starts `appl_`).
 */
export const REVENUECAT_IOS_API_KEY = "";

export type PaywallRequest = {
  /** Product id the paywall should highlight (from the 402 body). */
  product: string;
  /** Which quota ran out, for the explanatory copy. */
  kind: string;
};

type BillingState = {
  /** Server-side entitlement snapshot; null until the first load. */
  status: BillingStatus | null;
  loading: boolean;
  /** True once the RevenueCat SDK is configured (needs a key + a native build). */
  storeReady: boolean;
  /** Store products by product id, for prices/titles on the paywall. */
  products: Record<string, PurchasesStoreProduct>;
  /** Set while the paywall should be showing; null when it shouldn't. */
  paywall: PaywallRequest | null;
  refresh: () => Promise<void>;
  /** Open the paywall by hand (e.g. an "Upgrade" menu item). */
  showPaywall: (request?: Partial<PaywallRequest>) => void;
  hidePaywall: () => void;
  /** Buy a product. Resolves true on success, false if the user cancelled. */
  purchase: (productId: string) => Promise<boolean>;
  /** App Review requires this to be reachable from the paywall. */
  restore: () => Promise<void>;
};

const BillingContext = createContext<BillingState | undefined>(undefined);

/** Configure the SDK, hold entitlement state, and own the paywall's visibility. */
export function BillingProvider({ children }: { children: React.ReactNode }) {
  const { me } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [storeReady, setStoreReady] = useState(false);
  const [products, setProducts] = useState<Record<string, PurchasesStoreProduct>>({});
  const [paywall, setPaywall] = useState<PaywallRequest | null>(null);
  const configuredFor = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    if (!me) {
      setStatus(null);
      return;
    }
    setLoading(true);
    try {
      setStatus(await BillingApi.status());
    } catch {
      // A billing outage must never block the app: leaving `status` as-is
      // means quota badges go stale, not that the user is locked out. The
      // server still enforces on every metered call.
    } finally {
      setLoading(false);
    }
  }, [me]);

  // --- SDK configuration -----------------------------------------------------
  // Configure once per signed-in user, with users.id as the App User ID. On a
  // user switch (sign out -> sign in as someone else) logIn re-points the SDK
  // so purchases can never be attributed to the previous account.
  useEffect(() => {
    if (!me || !REVENUECAT_IOS_API_KEY || Platform.OS === "web") return;
    if (configuredFor.current === me.id) return;
    (async () => {
      try {
        if (__DEV__) Purchases.setLogLevel(LOG_LEVEL.WARN);
        if (configuredFor.current === null) {
          Purchases.configure({ apiKey: REVENUECAT_IOS_API_KEY, appUserID: me.id });
        } else {
          await Purchases.logIn(me.id);
        }
        configuredFor.current = me.id;
        setStoreReady(true);
      } catch {
        setStoreReady(false);
      }
    })();
  }, [me]);

  // Load prices for whatever product ids the server advertises, so the paywall
  // shows real localized App Store prices rather than hardcoded dollars.
  useEffect(() => {
    const ids = Object.values(status?.products ?? {});
    if (!storeReady || ids.length === 0) return;
    (async () => {
      try {
        const found = await Purchases.getProducts(ids);
        setProducts(Object.fromEntries(found.map((p) => [p.identifier, p])));
      } catch {
        setProducts({});
      }
    })();
  }, [storeReady, status?.products]);

  // First load + reload whenever the signed-in user changes.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // --- Central 402 -> paywall routing ---------------------------------------
  // api.ts throws QuotaError for any 402 and calls this handler on the way out,
  // so a newly metered endpoint needs no screen changes to be covered.
  useEffect(() => {
    const unsubscribe = setPaywallHandler((error: QuotaError) => {
      setPaywall({ product: error.paywall, kind: error.kind });
      refresh();  // the 402 means our cached quota is stale
    });
    return unsubscribe;
  }, [refresh]);

  const showPaywall = useCallback((request?: Partial<PaywallRequest>) => {
    setPaywall({
      product: request?.product
        ?? status?.products?.starter
        ?? "steel_starter_unlock",
      kind: request?.kind ?? "equipment_scan",
    });
  }, [status?.products]);

  const hidePaywall = useCallback(() => setPaywall(null), []);

  const purchase = useCallback(async (productId: string): Promise<boolean> => {
    if (!storeReady) throw new Error("In-app purchases aren't available on this build yet.");
    const product = products[productId] ?? (await Purchases.getProducts([productId]))[0];
    if (!product) throw new Error("That product isn't available from the App Store right now.");
    try {
      await Purchases.purchaseStoreProduct(product);
    } catch (e) {
      // A cancel is not an error worth showing — the user knows what they did.
      if ((e as { userCancelled?: boolean }).userCancelled) return false;
      throw e;
    }
    // Reconcile server-side straight away rather than waiting for the webhook,
    // then re-read the entitlement the server just wrote.
    try {
      setStatus(await BillingApi.sync());
    } catch {
      await refresh();
    }
    setPaywall(null);
    return true;
  }, [products, refresh, storeReady]);

  const restore = useCallback(async () => {
    if (!storeReady) throw new Error("In-app purchases aren't available on this build yet.");
    await Purchases.restorePurchases();
    try {
      setStatus(await BillingApi.sync());
    } catch {
      await refresh();
    }
  }, [refresh, storeReady]);

  const value = useMemo<BillingState>(() => ({
    status, loading, storeReady, products, paywall,
    refresh, showPaywall, hidePaywall, purchase, restore,
  }), [status, loading, storeReady, products, paywall,
       refresh, showPaywall, hidePaywall, purchase, restore]);

  return <BillingContext.Provider value={value}>{children}</BillingContext.Provider>;
}

/** Access billing state; must be called under a BillingProvider. */
export function useBilling(): BillingState {
  const ctx = useContext(BillingContext);
  if (!ctx) throw new Error("useBilling must be used within BillingProvider");
  return ctx;
}

/** Short quota label for a Badge/Chip, or null when there's nothing to say. */
export function quotaLabel(remaining: number | undefined, noun: string): string | null {
  if (remaining === undefined || remaining === null) return null;
  if (remaining < 0) return "Unlimited";
  return `${remaining} ${noun}${remaining === 1 ? "" : "s"} left`;
}
