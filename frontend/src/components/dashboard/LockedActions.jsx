import { Lock } from "lucide-react";
import { Button } from "@/components/ui/Button";

/**
 * Replaces a result card's edit/copy/export controls when the extraction isn't
 * owned by an account yet (the landing-page demo). The extracted fields stay
 * fully visible — only taking the data away is gated.
 */
export function LockedActions({ onClick }) {
  return (
    <Button size="sm" to="/signup" onClick={onClick}>
      <Lock size={14} /> Sign up free to export
    </Button>
  );
}
