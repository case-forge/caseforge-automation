
import type { FirmProfile } from "./firm";

export const ADMIN_LINK_DEFAULTS = {
  glitchtip: "https://glitchtip.example.net",
} as const;

export const EXPORT_BOARD_DEFAULT = "https://export.example.net";

export const FIRM_DEFAULTS: FirmProfile = {
  short_name: "EFL",
  workers: ["Alex", "Sam", "Jordan", "Riley", "Morgan"],
  hostnames: {
    crm: "example.net",
    chat: "chat.example.net",
    sign: "sign.example.net",
    demo: "demo.example.net",
  },
};
