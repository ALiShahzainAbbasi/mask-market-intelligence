import type { components } from "@mask/schemas";

export type Readiness = components["schemas"]["Readiness"];
export type HealthResult =
  | { kind: "received"; readiness: Readiness }
  | { kind: "unavailable"; reason: "connection" | "invalid_response" };

export function isReadiness(value: unknown): value is Readiness {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  if (candidate.status !== "ready" && candidate.status !== "not_ready") return false;
  if (typeof candidate.dependencies !== "object" || candidate.dependencies === null) return false;
  const deps = candidate.dependencies as Record<string, unknown>;
  if (Object.keys(deps).length !== 1 || ![deps.postgres].every((v) => v === "up" || v === "down"))
    return false;
  return (candidate.status === "ready") === (deps.postgres === "up");
}

export function validateApiBaseUrl(value: string): string {
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error("MASK_API_BASE_URL must be an HTTP(S) origin without credentials or path");
  }
  return url.origin;
}

export async function fetchReadiness(
  baseUrl: string,
  fetcher: typeof fetch = fetch,
): Promise<HealthResult> {
  // Configuration errors intentionally fail fast, not a fake healthy response.
  const origin = validateApiBaseUrl(baseUrl);
  try {
    const response = await fetcher(origin + "/health/ready", {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    if (![200, 503].includes(response.status))
      return { kind: "unavailable", reason: "invalid_response" };
    const value: unknown = await response.json();
    if (!isReadiness(value) || (response.status === 200) !== (value.status === "ready")) {
      return { kind: "unavailable", reason: "invalid_response" };
    }
    return { kind: "received", readiness: value };
  } catch {
    return { kind: "unavailable", reason: "connection" };
  }
}
