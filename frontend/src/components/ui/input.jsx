import * as React from "react";

import { cn } from "../../lib/utils";

export const Input = React.forwardRef(({ className, ...props }, ref) => {
  return <input className={cn("input", className)} ref={ref} {...props} />;
});

Input.displayName = "Input";
