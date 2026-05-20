import { Input } from "../ui/input";
import { Label } from "../ui/label";

export function FormField({ id, label, ...inputProps }) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={id} {...inputProps} />
    </div>
  );
}
