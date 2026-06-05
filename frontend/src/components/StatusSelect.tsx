import { STATUS_OPTIONS } from "@/lib/ratings";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NONE = "__none__";

interface Props {
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}

export default function StatusSelect({ value, onChange, disabled }: Props) {
  return (
    <Select
      value={value ?? NONE}
      disabled={disabled}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
    >
      <SelectTrigger className="w-44">
        <SelectValue placeholder="No status" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>No status</SelectItem>
        {STATUS_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
