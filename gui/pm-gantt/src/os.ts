/** True for macOS / Mac-like UA (close control on the leading side). */
export function isMacLike(): boolean {
  if (typeof navigator === "undefined") return false;
  const p = (navigator.platform ?? "").toLowerCase();
  const ua = navigator.userAgent.toLowerCase();
  return p.includes("mac") || ua.includes("mac os");
}
