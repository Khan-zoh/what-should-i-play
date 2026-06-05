import type { LibraryItem } from "@/lib/api";
import { labelForStatus, labelForValue } from "@/lib/ratings";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Props {
  item: LibraryItem;
  onQuickRate: (item: LibraryItem) => void;
}

export default function GameCard({ item, onQuickRate }: Props) {
  return (
    <Card className="overflow-hidden flex flex-col">
      <div className="aspect-[3/4] bg-muted">
        {item.cover_url ? (
          <img
            src={item.cover_url}
            alt={item.name}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
            No cover
          </div>
        )}
      </div>
      <CardContent className="space-y-2 p-3">
        <h3 className="line-clamp-2 font-medium leading-tight">{item.name}</h3>
        <div className="flex flex-wrap gap-1 text-xs">
          <Badge variant="secondary">{item.hours_played.toFixed(0)}h</Badge>
          {item.enjoyment !== null && (
            <Badge>{labelForValue(item.enjoyment)}</Badge>
          )}
          {item.status !== null && (
            <Badge variant="outline">{labelForStatus(item.status)}</Badge>
          )}
        </div>
      </CardContent>
      <CardFooter className="mt-auto p-3 pt-0">
        <Button
          size="sm"
          variant="outline"
          className="w-full"
          onClick={() => onQuickRate(item)}
        >
          Rate / status
        </Button>
      </CardFooter>
    </Card>
  );
}
