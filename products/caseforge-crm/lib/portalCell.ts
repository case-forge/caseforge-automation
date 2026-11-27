
import type { StatusBoardItem } from "./matterMilestones";

export const PORTAL_TITLE = "Filed through the court's online portal";

export function showsPortal(item: Pick<StatusBoardItem, "portal_court">, column: string, cellValue: string): boolean {
  return column === "filed" && !cellValue && item.portal_court === true;
}
