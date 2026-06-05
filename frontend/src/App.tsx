import { Routes, Route } from "react-router-dom";
import AppShell from "@/components/AppShell";
import LibraryPage from "@/pages/LibraryPage";
import PreferencesPage from "@/pages/PreferencesPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LibraryPage />} />
        <Route path="preferences" element={<PreferencesPage />} />
      </Route>
    </Routes>
  );
}
