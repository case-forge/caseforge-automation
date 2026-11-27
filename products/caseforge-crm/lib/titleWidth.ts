
export function textWidth(text: string, font: string, measure?: (text: string, font: string) => number): number {
  if (measure) return measure(text, font);
  if (typeof document !== "undefined") {
    const ctx = document.createElement("canvas").getContext("2d");
    if (ctx) {
      ctx.font = font;
      return ctx.measureText(text).width;
    }
  }
  return text.length * 8;
}

export function minWidthFor(input: {
  titleText: string;
  font: string;

  otherWidths: number[];
  gap: number;
  padding: number;
  border: number;
  measure?: (text: string, font: string) => number;
}): number {
  const title = textWidth(input.titleText, input.font, input.measure);
  const items = input.otherWidths.length + 1;
  const others = input.otherWidths.reduce((n, w) => n + w, 0);
  return Math.ceil(title + others + input.gap * (items - 1) + input.padding + input.border);
}
