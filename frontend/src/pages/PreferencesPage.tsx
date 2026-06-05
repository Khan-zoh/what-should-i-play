import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet, apiPut, type Preferences } from "@/lib/api";
import PreferencesForm from "@/components/PreferencesForm";
import { Button } from "@/components/ui/button";

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    apiGet<Preferences>("/api/preferences").then(setPrefs);
  }, []);

  if (!prefs) return <p>Loading preferences...</p>;

  const save = async () => {
    await apiPut("/api/preferences", prefs);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="max-w-2xl space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Preferences</h1>
        <Button variant="outline" size="sm" onClick={() => navigate("/onboarding")}>
          Re-run setup
        </Button>
      </div>

      <PreferencesForm value={prefs} onChange={setPrefs} />

      <div className="flex items-center gap-3">
        <Button onClick={save}>Save preferences</Button>
        {saved && <span className="text-sm text-green-600">Saved</span>}
      </div>
    </div>
  );
}
