import { BackToHome } from "./BackToHome";
import type { ReactNode } from "react";

export function FirmPage({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <main className={wide ? "firm-page firm-page--wide" : "firm-page"}>
      <p>
        <BackToHome />
      </p>
      {children}
    </main>
  );
}
