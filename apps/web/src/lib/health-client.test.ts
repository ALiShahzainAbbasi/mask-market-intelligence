import { describe, expect, it, vi } from "vitest";
import { fetchReadiness, isReadiness, validateApiBaseUrl } from "./health-client";

describe("typed health boundary", () => {
  it("accepts a genuine 503 dependency response", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "not_ready", dependencies: { postgres: "down" } }), {
        status: 503,
      }),
    );
    expect((await fetchReadiness("http://api:8000", fetcher)).kind).toBe("received");
    expect(fetcher).toHaveBeenCalledWith(
      "http://api:8000/health/ready",
      expect.objectContaining({ cache: "no-store" }),
    );
  });
  it("rejects inconsistent/malformed readiness", () => {
    expect(isReadiness({ status: "ready", dependencies: { postgres: "down" } })).toBe(false);
    expect(
      isReadiness({ status: "ready", dependencies: { postgres: "up", unexpected: "up" } }),
    ).toBe(false);
    expect(isReadiness({ status: "ready" })).toBe(false);
    expect(isReadiness(null)).toBe(false);
  });
  it("handles connection failure without exposing details", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("secret"));
    expect(await fetchReadiness("http://localhost:8000", fetcher)).toEqual({
      kind: "unavailable",
      reason: "connection",
    });
  });
  it("rejects invalid HTTP payloads", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"message":"wrong"}'));
    expect(await fetchReadiness("http://localhost:8000", fetcher)).toEqual({
      kind: "unavailable",
      reason: "invalid_response",
    });
  });
  it.each(["ftp://host", "http://user:password@host", "http://host/path", "http://host?x=1"])(
    "rejects invalid config %s",
    (value) => {
      expect(() => validateApiBaseUrl(value)).toThrow();
    },
  );
});
