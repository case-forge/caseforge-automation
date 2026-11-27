import { FirmPage } from "@/components/FirmPage";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <FirmPage>
      <h1>Page not found</h1>
      <p>There is no page at this address. It may have moved or been removed.</p>
    </FirmPage>
  );
}
