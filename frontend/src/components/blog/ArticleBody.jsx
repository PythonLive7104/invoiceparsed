/**
 * Renders an article's content blocks (from the registry) to JSX.
 * Block shapes: { h2 } | { p } | { ul: [] } | { ol: [] }.
 * The prerenderer renders the same blocks to static HTML (see scripts/prerender.mjs),
 * keeping the SPA and crawler-visible content identical.
 */
export function ArticleBody({ blocks = [] }) {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.h2) return <h2 key={i} className="text-xl font-semibold text-white">{b.h2}</h2>;
        if (b.p) return <p key={i}>{b.p}</p>;
        if (b.ul)
          return (
            <ul key={i} className="list-disc space-y-1.5 pl-5 marker:text-brand-400">
              {b.ul.map((li, j) => <li key={j}>{li}</li>)}
            </ul>
          );
        if (b.ol)
          return (
            <ol key={i} className="list-decimal space-y-1.5 pl-5 marker:text-slate-500">
              {b.ol.map((li, j) => <li key={j}>{li}</li>)}
            </ol>
          );
        return null;
      })}
    </>
  );
}
