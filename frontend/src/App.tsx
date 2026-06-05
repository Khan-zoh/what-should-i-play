import { Routes, Route } from "react-router-dom";
import OnboardingGuard from "@/components/OnboardingGuard";
import AppShell from "@/components/AppShell";
import LibraryPage from "@/pages/LibraryPage";
import PreferencesPage from "@/pages/PreferencesPage";
import OnboardingWizard from "@/pages/OnboardingWizard";

export default function App() {
  return (
    <OnboardingGuard>
      <Routes>
        <Route path="/onboarding" element={<OnboardingWizard />} />
        <Route element={<AppShell />}>
          <Route index element={<LibraryPage />} />
          <Route path="preferences" element={<PreferencesPage />} />
        </Route>
      </Routes>
    </OnboardingGuard>
  );
}
