/**
 * safeSrc — Permanent architecture-level fix for the React empty-src warning.
 *
 * React warns when `src=""` is passed to <img>, <video>, <audio>, <iframe>,
 * or <source> because the browser will re-download the current page.
 *
 * Rule: A media element must either have a valid, non-empty src OR not be
 * rendered at all. Never pass `src=""` or `src={value || ""}`.
 *
 * Usage:
 *   <video src={safeSrc(url)} />          // returns undefined when url is empty
 *   {safeSrc(url) && <img src={safeSrc(url)} />}
 */

/**
 * Converts any falsy or whitespace-only value to `undefined`.
 * When `undefined` is passed as a prop React omits the attribute entirely,
 * preventing the browser from making a spurious network request.
 *
 * @param src  Raw src value from state, props, or API response
 * @returns    A trimmed non-empty string, or `undefined`
 */
export function safeSrc(src?: string | null | undefined): string | undefined {
  if (src === null || src === undefined) return undefined;
  if (typeof src !== "string") return undefined;
  const trimmed = src.trim();
  if (!trimmed.length) return undefined;
  return trimmed;
}

/**
 * Returns true only when the src is a valid, non-empty, non-whitespace string.
 * Use this as a render guard:
 *   {hasSrc(url) && <video src={url} />}
 */
export function hasSrc(src?: string | null | undefined): src is string {
  return safeSrc(src) !== undefined;
}

/**
 * Sanitizes an entire object's media URL fields in-place.
 * Converts empty strings to undefined so they never reach JSX.
 *
 * @param obj   An object from an API response
 * @param keys  The keys that are media URLs (e.g. ["video_url", "avatar"])
 * @returns     The same object reference, with empty URL fields set to undefined
 */
export function sanitizeMediaFields<T extends Record<string, unknown>>(
  obj: T,
  keys: (keyof T)[]
): T {
  for (const key of keys) {
    const val = obj[key];
    if (typeof val === "string") {
      (obj as Record<string, unknown>)[key as string] = safeSrc(val);
    }
  }
  return obj;
}

export default safeSrc;
