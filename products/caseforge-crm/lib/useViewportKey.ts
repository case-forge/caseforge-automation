"use client";

import { useEffect, useState } from "react";

export function useViewportKey(): number {
  const [key, setKey] = useState(0);
  useEffect(() => {
    const onResize = () => setKey((k) => k + 1);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return key;
}
