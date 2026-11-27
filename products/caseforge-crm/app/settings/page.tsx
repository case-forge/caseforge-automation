import { FirmPage } from "@/components/FirmPage";
import { SettingsPage } from "@/components/SettingsPage";

export const metadata = { title: "Settings" };

export default function Page() {
  return (
    <FirmPage>
      <SettingsPage />
    </FirmPage>
  );
}
