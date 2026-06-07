import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { JsonLd } from "@/components/seo/JsonLd";
import { faqPageSchema } from "@/lib/schema";
import { cn } from "@/lib/utils";

/**
 * Accessible FAQ accordion that ALSO emits FAQPage JSON-LD from the same data —
 * keeping the visible content and structured data in sync (a Google requirement:
 * FAQ schema must match on-page content).
 *
 * Props:
 *   faqs        array of { q, a }
 *   title       optional heading (default "Frequently asked questions")
 *   emitSchema  set false when the page already renders FAQPage schema elsewhere
 */
export function FaqSection({ faqs = [], title = "Frequently asked questions", emitSchema = true }) {
  const [open, setOpen] = useState(0);
  if (!faqs.length) return null;

  return (
    <section aria-labelledby="faq-heading" className="mx-auto w-full max-w-3xl">
      {emitSchema && <JsonLd data={faqPageSchema(faqs)} />}
      <h2 id="faq-heading" className="text-2xl font-semibold tracking-tight text-white">
        {title}
      </h2>
      <dl className="mt-6 divide-y divide-white/10 border-t border-white/10">
        {faqs.map((item, i) => {
          const isOpen = open === i;
          return (
            <div key={i} className="py-2">
              <dt>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? -1 : i)}
                  className="flex w-full items-center justify-between gap-4 py-3 text-left text-base font-medium text-white"
                >
                  {item.q}
                  <ChevronDown
                    size={18}
                    className={cn("shrink-0 text-slate-400 transition-transform", isOpen && "rotate-180")}
                  />
                </button>
              </dt>
              <dd
                className={cn(
                  "grid overflow-hidden text-sm text-slate-400 transition-all duration-200",
                  isOpen ? "grid-rows-[1fr] pb-4" : "grid-rows-[0fr]",
                )}
              >
                <div className="min-h-0 leading-relaxed">{item.a}</div>
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
