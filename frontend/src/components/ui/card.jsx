import { cn } from "../../lib/utils";

export function Card({ className, ...props }) {
  return <section className={cn("w-full max-w-[460px] rounded-lg border bg-card text-card-foreground shadow-[0_18px_60px_rgba(22,32,50,0.10)]", className)} {...props} />;
}

export function CardHeader({ className, ...props }) {
  return <div className={cn("p-[22px] pb-2", className)} {...props} />;
}

export function CardTitle({ className, ...props }) {
  return <h1 className={cn("flex items-center gap-2 text-xl leading-tight", className)} {...props} />;
}

export function CardDescription({ className, ...props }) {
  return <p className={cn("mt-2 leading-relaxed text-muted-foreground", className)} {...props} />;
}

export function CardContent({ className, ...props }) {
  return <div className={cn("p-[22px] py-2.5", className)} {...props} />;
}

export function CardFooter({ className, ...props }) {
  return <div className={cn("grid gap-3.5 p-[22px] pt-3", className)} {...props} />;
}
