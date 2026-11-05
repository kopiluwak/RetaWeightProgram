// Lightweight navigation context so any screen can jump Home without threading a
// callback through every component. Provided only for the authenticated app area
// (not the auth/onboarding flow), so ScreenBackground shows the Home control only
// where "home" is a valid destination.
import { createContext, useContext } from "react";

export type Nav = { goHome: () => void };

export const NavContext = createContext<Nav | null>(null);

/** null when outside the authenticated app (auth/onboarding). */
export function useNav(): Nav | null {
  return useContext(NavContext);
}
