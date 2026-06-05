import type { LibraryItem } from "@/lib/api";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import RatingControl from "@/components/RatingControl";
import StatusSelect from "@/components/StatusSelect";

interface Props {
  item: LibraryItem | null;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onRate: (item: LibraryItem, value: number | null) => void;
  onStatus: (item: LibraryItem, status: string | null) => void;
}

export default function QuickRatePanel({
  item,
  pending,
  onOpenChange,
  onRate,
  onStatus,
}: Props) {
  return (
    <Sheet open={item !== null} onOpenChange={onOpenChange}>
      <SheetContent>
        {item && (
          <>
            <SheetHeader>
              <SheetTitle>{item.name}</SheetTitle>
            </SheetHeader>
            <div className="mt-6 space-y-6">
              <div className="space-y-2">
                <p className="text-sm font-medium">How much did you enjoy it?</p>
                <RatingControl
                  value={item.enjoyment}
                  disabled={pending}
                  onChange={(v) => onRate(item, v)}
                />
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Status</p>
                <StatusSelect
                  value={item.status}
                  disabled={pending}
                  onChange={(s) => onStatus(item, s)}
                />
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
