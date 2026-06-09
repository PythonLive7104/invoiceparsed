import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { cn } from "@/lib/utils";

const links = [
  { href: "#features", label: "Features" },
  { href: "#how", label: "How it works" },
  { href: "#pricing", label: "Pricing" },
  { href: "#api", label: "API" },
];

export function MarketingNav() {
  const { user } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-all duration-300",
        scrolled
          ? "border-b border-white/[0.06] bg-ink-950/70 backdrop-blur-xl"
          : "border-b border-transparent",
      )}
    >
      <nav className="container-page flex h-16 items-center justify-between">
        <Logo />

        <div className="hidden items-center gap-1 md:flex">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-lg px-3.5 py-2 text-sm text-slate-300 transition-colors hover:text-white"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-2 md:flex">
          {user ? (
            <Button to="/dashboard" size="sm">
              Go to dashboard
            </Button>
          ) : (
            <>
              <Button to="/login" variant="ghost" size="sm">
                Sign in
              </Button>
              <Button to="/signup" size="sm">
                Start free
              </Button>
            </>
          )}
        </div>

        <button
          className="grid h-10 w-10 place-items-center rounded-lg text-slate-200 hover:bg-white/[0.06] md:hidden"
          onClick={() => setOpen((o) => !o)}
          aria-label="Toggle menu"
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </nav>

      {open && (
        <div className="border-t border-white/[0.06] bg-ink-950/95 px-5 py-4 md:hidden">
          <div className="flex flex-col gap-1">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm text-slate-300 hover:bg-white/[0.06] hover:text-white"
              >
                {l.label}
              </a>
            ))}
            {user ? (
              <Button to="/dashboard" size="sm" className="mt-2">
                Go to dashboard
              </Button>
            ) : (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button to="/login" variant="secondary" size="sm">
                  Sign in
                </Button>
                <Button to="/signup" size="sm">
                  Start free
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
