import { useState } from "react";
import { Mail, User as UserIcon, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { Button } from "@/components/ui/Button";
import { SEO } from "@/components/seo/SEO";
import { api, apiError } from "@/lib/api";

export default function Contact() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [state, setState] = useState("idle"); // idle|sending|sent|error
  const [error, setError] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    setState("sending");
    setError(null);
    try {
      await api.post("/api/contact", { name, email, message });
      setState("sent");
    } catch (err) {
      setError(apiError(err, "Couldn't send your message."));
      setState("error");
    }
  }

  return (
    <div className="min-h-screen bg-ink-950">
      <SEO
        title="Contact InvoiceParsed"
        description="Get in touch with the InvoiceParsed team — questions about invoice, receipt or bank statement extraction, pricing, the API, or your account."
        path="/contact"
      />
      <MarketingNav />

      <main className="mx-auto w-full max-w-xl px-5 pb-20 pt-28">
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Contact us</h1>
        <p className="mt-4 text-lg leading-relaxed text-slate-300">
          Questions about features, pricing, the API, or your account? Send us a message and we'll
          get back to you. You can also email{" "}
          <a href="mailto:invoiceparsed@gmail.com" className="text-brand-300 hover:text-brand-200">
            invoiceparsed@gmail.com
          </a>.
        </p>

        {state === "sent" ? (
          <div className="mt-10 glass rounded-2xl p-8 text-center">
            <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-emerald-500/15 text-emerald-300">
              <CheckCircle2 size={24} />
            </div>
            <h2 className="text-xl font-semibold text-white">Message sent</h2>
            <p className="mt-2 text-sm text-slate-400">
              Thanks{ name ? `, ${name.split(" ")[0]}` : "" }! We've received your message and will reply by email soon.
            </p>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="mt-10 glass rounded-2xl p-6 sm:p-8 space-y-4">
            <Field icon={<UserIcon size={16} />} label="Name" value={name} onChange={setName} placeholder="Your name" />
            <Field icon={<Mail size={16} />} label="Email" type="email" required value={email} onChange={setEmail} placeholder="you@example.com" />
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-300">Message</span>
              <textarea
                required
                rows={5}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="How can we help?"
                className="w-full rounded-xl border border-white/10 bg-ink-900/60 px-3.5 py-3 text-sm text-white placeholder:text-slate-600 outline-none transition-colors focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
              />
            </label>

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-300">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                {error}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={state === "sending"}>
              {state === "sending" && <Loader2 size={16} className="animate-spin" />}
              Send message
            </Button>
          </form>
        )}
      </main>
      <Footer />
    </div>
  );
}

function Field({ icon, label, value, onChange, ...rest }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">{icon}</span>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none transition-colors focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          {...rest}
        />
      </span>
    </label>
  );
}
