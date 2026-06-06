import { BillingPlans } from "@/components/dashboard/BillingPlans";
import { UsageMeter } from "@/components/dashboard/UsageMeter";
import { useAuth } from "@/lib/auth.jsx";

export default function Billing() {
  const { usage } = useAuth();
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          Billing & plans
        </h1>
        <p className="mt-1.5 text-slate-400">
          Manage your subscription. Upgrade when invoices pile up.
        </p>
      </div>

      <div className="max-w-md">
        <UsageMeter usage={usage} />
      </div>

      <BillingPlans />
    </div>
  );
}
