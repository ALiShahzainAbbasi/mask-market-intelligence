import { SystemStatus } from "@/components/system-status";
import { fetchReadiness } from "@/lib/health-client";
export const dynamic = "force-dynamic";

export default async function Page() {
  const result = await fetchReadiness(process.env.MASK_API_BASE_URL ?? "http://127.0.0.1:8000");
  return <SystemStatus result={result} />;
}
