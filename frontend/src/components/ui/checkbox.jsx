import * as React from "react";

import { cn } from "../../lib/utils";

export const Checkbox = React.forwardRef(({ className, ...props }, ref) => {
  return <input className={cn("checkbox", className)} ref={ref} type="checkbox" {...props} />;
});

Checkbox.displayName = "Checkbox";
