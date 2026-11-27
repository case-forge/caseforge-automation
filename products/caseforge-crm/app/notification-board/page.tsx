import { FirmPage } from "@/components/FirmPage";
import { NotificationBoardPage } from "@/components/FirmPageViews";

export const metadata = { title: "Notification Board" };

export default function Page() {
  return (
    <FirmPage>
      <NotificationBoardPage />
    </FirmPage>
  );
}
