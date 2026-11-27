import { BackToHome } from "@/components/BackToHome";
import { BillingChart } from "@/components/BillingChart";

export const metadata = { title: "Billing by Day" };

export default function BillingChartPage() {
  return (
    <main className="billing-chart-page">
      <p>
        <BackToHome />
      </p>
      <BillingChart />
    </main>
  );
}
