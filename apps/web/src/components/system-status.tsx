import type { HealthResult } from "@/lib/health-client";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function SystemStatus({ result }: { result: HealthResult }) {
  const connected = result.kind === "received";
  const ready = connected && result.readiness.status === "ready";
  const services = [
    { name: "FastAPI", detail: "Application service", up: connected },
    {
      name: "PostgreSQL + pgvector",
      detail: "Database, extension & migration",
      up: connected ? result.readiness.dependencies.postgres === "up" : null,
    },
  ];
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-12 md:py-20">
      <header className="mb-12 flex items-center justify-between border-b border-border pb-6">
        <span className="font-mono text-xl font-bold tracking-tight">
          MASK<span className="text-primary"> / </span>AI
        </span>
        <span className="rounded-full border border-border px-3 py-1 font-mono text-xs text-muted-foreground">
          LOCAL DEVELOPMENT
        </span>
      </header>
      <div className="mb-8">
        <p className="mb-3 font-mono text-xs uppercase tracking-[0.18em] text-primary">
          Phase 01 · Infrastructure
        </p>
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">System status</h1>
        <p className="mt-4 max-w-xl leading-relaxed text-muted-foreground">
          The foundation for evidence-led market selection. This page checks service connectivity;
          it does not contain research or market scores.
        </p>
      </div>
      <Card aria-label="Service readiness">
        <CardHeader className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-semibold">
            {ready
              ? "Core dependencies ready"
              : connected
                ? "Dependencies need attention"
                : "API unavailable"}
          </h2>
          <span role="status" className={ready ? "text-sm text-primary" : "text-sm text-warning"}>
            {ready ? "Ready" : "Not ready"}
          </span>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border">
            {services.map((service) => (
              <li
                key={service.name}
                className="flex items-center justify-between gap-4 py-5 first:pt-0"
              >
                <div>
                  <p className="font-medium">{service.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{service.detail}</p>
                </div>
                <span
                  className={
                    "font-mono text-xs " + (service.up ? "text-primary" : "text-muted-foreground")
                  }
                >
                  {service.up === null ? "UNKNOWN" : service.up ? "CONNECTED" : "UNAVAILABLE"}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-4 border-t border-border pt-5 text-sm leading-relaxed text-muted-foreground">
            PostgreSQL also stores the durable queue. Worker execution and lease recovery are
            verified separately by the protected smoke-job test.
          </p>
        </CardContent>
      </Card>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p className="text-xs text-muted-foreground">
          No credentials are exposed by this status page.
        </p>
        <form action="/" method="get">
          <Button type="submit">Check again</Button>
        </form>
      </div>
      <footer className="mt-auto pt-16 text-xs text-muted-foreground">
        Market Intelligence & Selection System · Infrastructure only
      </footer>
    </main>
  );
}
