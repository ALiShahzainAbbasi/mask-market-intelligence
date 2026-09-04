import * as React from "react";
import { Slot } from "radix-ui";
import { cn } from "@/lib/utils";

export function Button({
  asChild = false,
  className,
  ...props
}: React.ComponentProps<"button"> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      className={cn(
        "inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-85 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
