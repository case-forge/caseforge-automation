import { FirmPage } from "@/components/FirmPage";
import { ScansPage } from "@/components/FirmPageViews";

export const metadata = { title: "Scans" };

export default function Page() {
  return (
    <FirmPage wide>
      <ScansPage />
    </FirmPage>
  );
}
