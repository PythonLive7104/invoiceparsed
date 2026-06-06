import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  History,
  CreditCard,
  Webhook,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { UsageMeter } from "@/components/dashboard/UsageMeter";
import { cn, initials } from "@/lib/utils";
import { useAuth } from "@/lib/auth.jsx";

const nav = [
  { to: "/dashboard", label: "Extract", icon: LayoutDashboard, end: true },
  { to: "/dashboard/history", label: "History", icon: History },
  { to: "/dashboard/api", label: "API & Webhooks", icon: Webhook },
  { to: "/dashboard/billing", label: "Billing", icon: CreditCard },
];

export default function DashboardShell() {
  const navigate = useNavigate();
  const { user, usage, logout } = useAuth();
  const [open, setOpen] = useState(false);

  function onLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="px-5 py-5">
        <Logo to="/dashboard" />
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                isActive
                  ? "bg-brand-500/15 text-white ring-1 ring-inset ring-brand-400/25"
                  : "text-slate-400 hover:bg-white/[0.04] hover:text-white",
              )
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 pb-3">
        <UsageMeter usage={usage} compact />
      </div>

      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-2">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-gradient text-xs font-semibold text-white">
            {initials(user?.name || user?.email || "?")}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-white">
              {user?.name || user?.email?.split("@")[0]}
            </div>
            <div className="truncate text-xs capitalize text-slate-500">{user?.plan} plan</div>
          </div>
          <button
            onClick={onLogout}
            title="Sign out"
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-white"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[268px_1fr]">
      <aside className="sticky top-0 hidden h-screen border-r border-white/[0.06] bg-ink-900/40 backdrop-blur-xl lg:block">
        {sidebar}
      </aside>

      <div className="flex items-center justify-between border-b border-white/[0.06] bg-ink-950/80 px-4 py-3 backdrop-blur-xl lg:hidden">
        <Logo to="/dashboard" />
        <button
          onClick={() => setOpen(true)}
          className="grid h-10 w-10 place-items-center rounded-lg text-slate-200 hover:bg-white/[0.06]"
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 top-0 h-full w-72 border-r border-white/10 bg-ink-900">
            <button
              onClick={() => setOpen(false)}
              className="absolute right-3 top-4 grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-white/[0.06]"
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
            {sidebar}
          </div>
        </div>
      )}

      <div className="min-w-0">
        <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 lg:py-10">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
