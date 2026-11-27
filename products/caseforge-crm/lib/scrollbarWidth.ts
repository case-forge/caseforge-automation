
export type MeasurableDocument = Pick<Document, "createElement" | "body">;

export function measureScrollbarWidth(doc: MeasurableDocument): number {
  const probe = doc.createElement("div");
  probe.style.position = "absolute";
  probe.style.top = "-9999px";
  probe.style.width = "100px";
  probe.style.height = "100px";
  probe.style.overflow = "scroll";
  doc.body.appendChild(probe);
  try {
    const width = probe.offsetWidth - probe.clientWidth;
    return Number.isFinite(width) && width > 0 && width < 40 ? Math.round(width) : 0;
  } finally {
    doc.body.removeChild(probe);
  }
}
