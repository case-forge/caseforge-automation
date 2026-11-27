import { FirmPage } from "@/components/FirmPage";
import { ClientLists } from "@/components/ClientLists";
import { listFromParam } from "@/lib/clientLists";

export const metadata = { title: "Client Lists" };

export default async function Page({ searchParams }: { searchParams: Promise<{ list?: string | string[] }> }) {
  const { list } = await searchParams;
  return (
    <FirmPage>
      <ClientLists initial={listFromParam(Array.isArray(list) ? list[0] : (list ?? null))} />
    </FirmPage>
  );
}
