
export const STUB_USER_COOKIE = "stub_user";
export const DEFAULT_STUB_USER = "stub-user";

export function stubUserFor(request: { headers: Headers }, remoteUser: string | null | undefined): string {
  const verified = (remoteUser ?? "").trim().toLowerCase();
  if (verified) return verified;
  const cookies = request.headers.get("cookie") ?? "";
  const match = new RegExp(`(?:^|;\\s*)${STUB_USER_COOKIE}=([^;]*)`).exec(cookies);
  const named = match ? decodeURIComponent(match[1]).trim().toLowerCase().replace(/[^a-z0-9@._+-]/g, "_").slice(0, 60) : "";
  return named || DEFAULT_STUB_USER;
}
