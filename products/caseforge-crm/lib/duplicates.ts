
export type DuplicatePair = {
  reason: string;
  a: { matter_id: string; client_name: string };
  b: { matter_id: string; client_name: string };
};
