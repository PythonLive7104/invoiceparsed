import { JsonLd } from "@/components/seo/JsonLd";
import { organizationSchema, websiteSchema } from "@/lib/schema";

/**
 * Site-wide Organization + WebSite JSON-LD. Render once near the app root so it
 * appears in <head> on every route.
 */
export function SiteSchema() {
  return <JsonLd data={[organizationSchema(), websiteSchema()]} />;
}
