import { useState } from "react";
import type { ForYouItem } from "@/lib/api";
import { DISMISS_REASONS } from "@/lib/dismissReasons";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  item: ForYouItem;
  busy: boolean;
  onClick: (item: ForYouItem) => void;
  onStartPlaying: (item: ForYouItem) => void;
  onDismiss: (item: ForYouItem, reason: string) => void;
}

export default function ForYouCard({
  item,
  busy,
  onClick,
  onStartPlaying,
  onDismiss,
}: Props) {
  const [showWhy, setShowWhy] = useState(false);

  return (
    <Card className="flex flex-col">
      <CardContent
        className="space-y-2 p-4"
        onClick={() => onClick(item)}
        role="button"
        tabIndex={0}
      >
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium leading-tight">{item.name}</h3>
          {item.critic_score !== null && (
            <Badge variant="secondary">{Math.round(item.critic_score)}</Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          {item.genres.map((g) => (
            <Badge key={g} variant="outline" className="text-xs">
              {g}
            </Badge>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">{item.explanation}</p>
        <button
          type="button"
          className="text-xs text-muted-foreground underline"
          onClick={(e) => {
            e.stopPropagation();
            setShowWhy((v) => !v);
          }}
        >
          {showWhy ? "Hide why" : "Why?"}
        </button>
        {showWhy && (
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {item.reason_codes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        )}
      </CardContent>
      <CardFooter className="mt-auto flex items-center gap-2 p-4 pt-0">
        <Button size="sm" disabled={busy} onClick={() => onStartPlaying(item)}>
          Start playing
        </Button>
        <Select
          disabled={busy}
          onValueChange={(reason) => onDismiss(item, reason)}
        >
          <SelectTrigger className="h-9 w-36">
            <SelectValue placeholder="Dismiss" />
          </SelectTrigger>
          <SelectContent>
            {DISMISS_REASONS.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardFooter>
    </Card>
  );
}
