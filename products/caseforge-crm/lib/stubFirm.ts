
export const DEMO_FIRM = {
  name: "Example Family Law LLP",
  short_name: "EFL",

  workers: ["Alex", "Sam", "Jordan", "Riley", "Morgan"] as readonly string[],

  principal_initials: "AE",
  folders: {
    unsorted_notes: "1AA-Temporary saved docs",
    common_scans: "Clients - Common Scanned Docs",
    read_only_book: "Clients - Protective Orders",
  },

  reference_prefix: "EFL",
} as const;

export const [DEMO_PRINCIPAL, DEMO_SECOND, DEMO_THIRD, DEMO_FOURTH, DEMO_FIFTH] = DEMO_FIRM.workers;
