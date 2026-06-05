import { NavLink, Outlet } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
    isActive
      ? "bg-secondary text-secondary-foreground"
      : "text-muted-foreground hover:text-foreground"
  }`;

export default function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <nav className="mx-auto flex max-w-6xl items-center gap-2 px-6 py-3">
          <span className="mr-4 text-lg font-semibold">What Should I Play?</span>
          <NavLink to="/" className={linkClass} end>
            Library
          </NavLink>
          <NavLink to="/preferences" className={linkClass}>
            Preferences
          </NavLink>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
