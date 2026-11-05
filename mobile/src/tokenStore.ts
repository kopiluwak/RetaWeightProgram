// Secure token storage (spec F4): refresh + access tokens live in the OS secure
// enclave via expo-secure-store. NEVER AsyncStorage (plaintext) — that would
// undercut the F8 encryption posture.
import * as SecureStore from "expo-secure-store";

const ACCESS_KEY = "wp_access_token";
const REFRESH_KEY = "wp_refresh_token";

/** Persist both tokens after login or a successful refresh rotation. */
export async function saveTokens(access: string, refresh: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_KEY, access);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

/** Wipe both tokens (logout or unrecoverable auth failure). */
export async function clearTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_KEY);
  await SecureStore.deleteItemAsync(REFRESH_KEY);
}
