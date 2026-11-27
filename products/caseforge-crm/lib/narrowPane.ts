
export const NARROW_LAYOUT_MAX_PX = 720;

export type NarrowPane = "results" | "detail";

export function narrowPane({
  clientOpen,
  showClient,
  resultsCollapsed,
}: {

  clientOpen: boolean;

  showClient: boolean;

  resultsCollapsed: boolean;
}): NarrowPane {

  if (resultsCollapsed) return "detail";
  return clientOpen && showClient ? "detail" : "results";
}
