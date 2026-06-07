import { InvoiceCard } from "@/components/dashboard/InvoiceCard";
import { ReceiptCard } from "@/components/dashboard/ReceiptCard";

/** Renders the right result card for an extraction's document type. */
export function ResultCard({ docType, ...props }) {
  return docType === "receipt" ? <ReceiptCard {...props} /> : <InvoiceCard {...props} />;
}
