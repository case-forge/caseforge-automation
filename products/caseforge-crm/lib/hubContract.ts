
import contract from "./hubContract.json";

type Schema = {
  $ref?: string;
  type?: string | string[];
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
  prefixItems?: Schema[];
  additionalProperties?: boolean | Schema;
  anyOf?: Schema[];
  oneOf?: Schema[];
  allOf?: Schema[];
  enum?: unknown[];
  const?: unknown;
};

const components = contract.components as unknown as Record<string, Schema>;
const routes = contract.routes as unknown as Record<string, Schema>;

export function hubResponseSchema(method: string, hubPath: string): Schema | undefined {
  return routes[`${method.toUpperCase()} ${hubPath}`];
}

export function hubRouteKeys(): string[] {
  return Object.keys(routes);
}

function resolve(schema: Schema): Schema {
  let current = schema;
  for (let hops = 0; current.$ref && hops < 20; hops += 1) {
    const found = components[current.$ref.replace("#/components/schemas/", "")];
    if (!found) throw new Error(`hub contract refers to an unknown component ${current.$ref}`);
    current = found;
  }
  return current;
}

function kind(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
  return typeof value;
}

function typeMatches(want: string, value: unknown): boolean {
  const got = kind(value);
  return want === got || (want === "number" && got === "integer");
}

export function validateAgainstHub(value: unknown, schema: Schema, path = "$"): string[] {
  const s = resolve(schema);
  if (s.anyOf || s.oneOf) {
    const branches = (s.anyOf ?? s.oneOf) as Schema[];
    const attempts = branches.map((branch) => validateAgainstHub(value, branch, path));
    if (attempts.some((problems) => problems.length === 0)) return [];

    const best = attempts.reduce((a, b) => (b.length < a.length ? b : a));
    return best.length === 1 ? best : [`${path}: matches none of the hub's ${branches.length} allowed shapes (closest: ${best.join("; ")})`];
  }
  if (s.allOf) return s.allOf.flatMap((part) => validateAgainstHub(value, part, path));
  if (s.const !== undefined && value !== s.const) return [`${path}: the hub sends ${JSON.stringify(s.const)}, the stub sends ${JSON.stringify(value)}`];
  if (s.enum && !s.enum.includes(value)) return [`${path}: ${JSON.stringify(value)} is not one of the hub's values ${JSON.stringify(s.enum)}`];

  const types = s.type === undefined ? [] : Array.isArray(s.type) ? s.type : [s.type];
  if (types.length && !types.some((t) => typeMatches(t, value))) {
    return [`${path}: the hub sends ${types.join(" or ")}, the stub sends ${kind(value)}`];
  }
  const problems: string[] = [];
  if (Array.isArray(value)) {
    if (s.items) value.forEach((item, i) => problems.push(...validateAgainstHub(item, s.items as Schema, `${path}[${i}]`)));
  } else if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    const props = s.properties ?? {};
    for (const name of s.required ?? []) {
      if (!(name in object)) problems.push(`${path}.${name}: the hub sends this field, the stub leaves it out`);
    }
    for (const [name, v] of Object.entries(object)) {
      if (name in props) problems.push(...validateAgainstHub(v, props[name], `${path}.${name}`));
      else if (s.additionalProperties && typeof s.additionalProperties === "object") {
        problems.push(...validateAgainstHub(v, s.additionalProperties, `${path}.${name}`));
      } else if (Object.keys(props).length && s.additionalProperties !== true && s.additionalProperties === undefined) {
        problems.push(`${path}.${name}: the stub sends this field, the hub's response has no such field`);
      }
    }
  }
  return problems;
}
