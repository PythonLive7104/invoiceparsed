import { InvoiceCard } from "@/components/dashboard/InvoiceCard";
import { ReceiptCard } from "@/components/dashboard/ReceiptCard";
import { StatementCard } from "@/components/dashboard/StatementCard";

/** Renders the right result card for an extraction's document type. */
export function ResultCard({ docType, ...props }) {
  if (docType === "receipt") return <ReceiptCard {...props} />;
  if (docType === "statement") return <StatementCard {...props} />;
  return <InvoiceCard {...props} />;
}
