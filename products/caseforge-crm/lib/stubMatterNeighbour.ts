
import { stubSearch } from "./stub";
import { neighbourIn } from "./matterNeighbour";

export function stubMatterNeighbour(matterId: string, dir: "prev" | "next"): string | null {
  const ids = stubSearch("stub").results.map((row) => String(row.matter_id ?? ""));
  return neighbourIn(ids, matterId, dir);
}
