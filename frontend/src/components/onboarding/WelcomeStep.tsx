import { Button } from "@/components/ui/button";

export default function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-4 text-center">
      <h1 className="text-3xl font-semibold">Welcome to What Should I Play?</h1>
      <p className="text-muted-foreground">
        Import your Steam library, tell us what you enjoy, and get tailored
        picks for what to play next.
      </p>
      <Button onClick={onNext}>Get started</Button>
    </div>
  );
}
