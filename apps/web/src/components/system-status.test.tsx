import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SystemStatus } from "./system-status";

describe("SystemStatus", () => {
  it("shows real dependency readiness without claiming worker completion", () => {
    render(
      <SystemStatus
        result={{
          kind: "received",
          readiness: { status: "ready", dependencies: { postgres: "up" } },
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Ready");
    expect(screen.getByText(/PostgreSQL also stores the durable queue/)).toBeInTheDocument();
  });
  it("shows unknown dependencies when API cannot be reached", () => {
    render(<SystemStatus result={{ kind: "unavailable", reason: "connection" }} />);
    expect(screen.getByText("API unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("UNKNOWN")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Check again" })).toHaveAttribute("type", "submit");
  });
  it("shows a dependency failure instead of a healthy screen", () => {
    render(
      <SystemStatus
        result={{
          kind: "received",
          readiness: { status: "not_ready", dependencies: { postgres: "down" } },
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Not ready");
  });
});
