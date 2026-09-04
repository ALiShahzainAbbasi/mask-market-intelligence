import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.ComponentProps<"section">) {
  return (
    <section
      className={cn("rounded-xl border border-border bg-card text-card-foreground", className)}
      {...props}
    />
  );
}
export function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("border-b border-border px-6 py-5", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("p-6", className)} {...props} />;
}
