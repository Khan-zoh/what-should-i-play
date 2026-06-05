import { RATING_OPTIONS } from "@/lib/ratings";
import { Button } from "@/components/ui/button";

interface Props {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

export default function RatingControl({ value, onChange, disabled }: Props) {
  return (
    <div className="flex flex-wrap gap-1">
      {RATING_OPTIONS.map((opt) => (
        <Button
          key={opt.value}
          size="sm"
          disabled={disabled}
          variant={value === opt.value ? "default" : "outline"}
          onClick={() => onChange(value === opt.value ? null : opt.value)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}
