import { CircleAlert, CircleCheck } from "lucide-react";

import { cn } from "../../lib/utils";

export function Alert({ className, variant = "default", ...props }) {
  return <div className={cn("alert", `alert-${variant}`, className)} role="alert" {...props} />;
}

export function AlertIcon({ variant = "default" }) {
  const Icon = variant === "success" ? CircleCheck : CircleAlert;
  return <Icon aria-hidden="true" size={18} />;
}

export function AlertDescription({ className, ...props }) {
  return <p className={cn("alert-description", className)} {...props} />;
}
