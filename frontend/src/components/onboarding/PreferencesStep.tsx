import { useEffect, useState } from "react";
import { apiGet, apiPut, type Preferences } from "@/lib/api";
import PreferencesForm from "@/components/PreferencesForm";
import { Button } from "@/components/ui/button";

export default function PreferencesStep({ onFinish }: { onFinish: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiGet<Preferences>("/api/preferences").then(setPrefs);
  }, []);

  if (!prefs) return <p>Loading preferences...</p>;

  const finish = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await apiPut("/api/preferences", prefs);
      onFinish();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">What do you enjoy?</h1>
        <p className="text-muted-foreground">
          This helps tailor your recommendations. You can change it anytime.
        </p>
      </div>
      <PreferencesForm value={prefs} onChange={setPrefs} />
      <Button onClick={finish} disabled={saving}>
        Finish
      </Button>
    </div>
  );
}
