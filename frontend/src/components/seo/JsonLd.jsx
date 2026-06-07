import { Helmet } from "react-helmet-async";

/**
 * Renders one or more JSON-LD blocks into <head>. Pass a single schema object
 * or an array; nullish entries are skipped. Uses Helmet so it works with SSR /
 * prerendering and is deduped per page.
 */
export function JsonLd({ data }) {
  const items = (Array.isArray(data) ? data : [data]).filter(Boolean);
  if (!items.length) return null;
  return (
    <Helmet>
      {items.map((schema, i) => (
        <script key={i} type="application/ld+json">
          {JSON.stringify(schema)}
        </script>
      ))}
    </Helmet>
  );
}
