import { CircleAlert, CircleCheck } from "lucide-react";

import { cn } from "../../lib/utils";

export function Alert({ className, variant = "default", ...props }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-md border p-3 text-sm leading-relaxed",
        variant === "success"
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-red-200 bg-red-50 text-destructive",
        className,
      )}
      role="alert"
      {...props}
    />
  );
}

export function AlertIcon({ variant = "default" }) {
  const Icon = variant === "success" ? CircleCheck : CircleAlert;
  return <Icon aria-hidden="true" size={18} />;
}

export function AlertDescription({ className, ...props }) {
  return <p className={cn("m-0", className)} {...props} />;
}
