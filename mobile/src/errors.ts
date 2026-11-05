// User-facing error copy. API calls throw Error(detail) where `detail` is the
// backend message (usually fine to show) or a low-level fetch failure (not).
// friendlyError() keeps readable server messages but swaps raw
// network/5xx noise for something actionable. Log the original separately.
export function friendlyError(
  e: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  const msg = e instanceof Error ? e.message.trim() : typeof e === "string" ? e.trim() : "";
  if (/network request failed|failed to fetch|network error|timeout|timed out/i.test(msg)) {
    return "Couldn't reach the server. Check your connection and try again.";
  }
  if (/request failed \(5\d\d\)|upload failed \(5\d\d\)|scan failed \(5\d\d\)|\b50\d\b/i.test(msg)) {
    return "The server had a problem. Please try again in a moment.";
  }
  if (/request failed \(401\)|not authenticated|unauthorized/i.test(msg)) {
    return "Your session expired. Please sign in again.";
  }
  return msg || fallback;
}
