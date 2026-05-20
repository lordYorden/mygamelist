import * as React from "react";

import { cn } from "../../lib/utils";

export const Checkbox = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <input
      className={cn("h-[18px] w-[18px] rounded border-input accent-primary", className)}
      ref={ref}
      type="checkbox"
      {...props}
    />
  );
});

Checkbox.displayName = "Checkbox";
