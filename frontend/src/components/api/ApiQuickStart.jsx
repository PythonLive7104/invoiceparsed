import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

/** Build language snippets for a given API base URL. */
export function buildSnippets(base) {
  return {
    cURL: `curl -X POST ${base}/api/extract \\
  -H "Authorization: Bearer ip_live_..." \\
  -F "file=@invoice.pdf" \\
  -F "doc_type=invoice"   # invoice | receipt | statement`,

    Python: `import requests

with open("invoice.pdf", "rb") as f:
    resp = requests.post(
        "${base}/api/extract",
        headers={"Authorization": "Bearer ip_live_..."},
        files={"file": f},
        data={"doc_type": "invoice"},  # invoice | receipt | statement
    )

resp.raise_for_status()
print(resp.json()["invoice"])`,

    "Node.js": `import fs from "node:fs";

const form = new FormData();
form.append("file", new Blob([fs.readFileSync("invoice.pdf")]), "invoice.pdf");
form.append("doc_type", "invoice"); // invoice | receipt | statement

const res = await fetch("${base}/api/extract", {
  method: "POST",
  headers: { Authorization: "Bearer ip_live_..." },
  body: form,
});

const data = await res.json();
console.log(data.invoice);`,
  };
}

export const SAMPLE_RESPONSE = `{
  "id": "a1b2c3...",
  "docType": "invoice",
  "fileName": "invoice.pdf",
  "status": "completed",
  "invoice": {
    "vendor": { "name": "Acme Corp", "address": "...", "email": "..." },
    "invoice_number": "INV-2024-0042",
    "invoice_date": "2024-03-15",
    "due_date": "2024-04-14",
    "currency": "USD",
    "line_items": [
      { "description": "Design work", "quantity": 2, "unit_price": 750, "amount": 1500 }
    ],
    "subtotal": 1500.00, "tax": 120.00, "total": 1620.00,
    "confidence": { "total": 0.99, "vendor": 0.97 }
  }
}`;

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]"
    >
      {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** Tabbed language snippets + sample response. Shared by the dashboard and the
 * public docs page. Pass the API base URL (e.g. https://invoiceparsed.com). */
export function ApiQuickStart({ base }) {
  const snippets = buildSnippets(base);
  const langs = Object.keys(snippets);
  const [lang, setLang] = useState(langs[0]);

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-white/10 bg-ink-950/70">
        <div className="flex items-center justify-between border-b border-white/[0.06] pl-2 pr-3">
          <div className="flex">
            {langs.map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={cn(
                  "px-3 py-2 text-xs font-medium transition-colors",
                  l === lang ? "text-white" : "text-slate-500 hover:text-slate-300",
                )}
              >
                {l}
                {l === lang && <span className="mt-1.5 block h-0.5 rounded-full bg-brand-400" />}
              </button>
            ))}
          </div>
          <CopyBtn text={snippets[lang]} />
        </div>
        <pre className="overflow-x-auto p-4 font-mono text-[12.5px] leading-relaxed text-slate-300">{snippets[lang]}</pre>
      </div>

      <div className="overflow-hidden rounded-xl border border-white/10 bg-ink-950/70">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
          <span className="text-[11px] text-slate-500">Example response (200 OK)</span>
          <CopyBtn text={SAMPLE_RESPONSE} />
        </div>
        <pre className="max-h-72 overflow-auto p-4 font-mono text-[12.5px] leading-relaxed text-slate-300">{SAMPLE_RESPONSE}</pre>
      </div>
    </div>
  );
}
