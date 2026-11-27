
export const LIVE_LABEL = "Home";

const TAILNET_ADDRESS = /^100\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;

function bareHost(host: string | null | undefined): string {
  const value = (host ?? "").trim().toLowerCase();
  if (value.startsWith("[")) return value.slice(1, value.indexOf("]") === -1 ? undefined : value.indexOf("]"));
  return value.split(":")[0];
}

export function isTailnetHost(host: string | null | undefined): boolean {
  const name = bareHost(host);
  return name.endsWith(".ts.net") || TAILNET_ADDRESS.test(name);
}

export function tabTitle(stub: boolean, host: string | null | undefined): { default: string; template: string } {
  const prefix = (isTailnetHost(host) ? "Tailnet " : "") + (stub ? "Demo " : "");
  return { default: stub ? prefix.trim() : prefix + LIVE_LABEL, template: `${prefix}%s` };
}

const BADGE = /^\(\d+\) /;

export function badgedTitle(title: string, unread: number): string {
  const plain = title.replace(BADGE, "");
  return unread > 0 ? `(${unread}) ${plain}` : plain;
}
