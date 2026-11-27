import { Workspace } from "@/components/Workspace";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Workspace />
      {children}
    </>
  );
}
