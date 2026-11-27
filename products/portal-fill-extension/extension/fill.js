
export async function fillPage(fields, options) {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const report = { refused: "", filled: [], left: [], absent: [], failed: [] };
  const KINDS = ["yesno", "text", "textarea", "date", "radio", "checkbox"];

  const byName = (name) => [...document.getElementsByName(name)];
  const boxes = (field) => {
    if (field.name !== undefined) {

      const part = (mark) => (field.name.endsWith("]") ? `${field.name.slice(0, -1)}(${mark})]` : `${field.name}(${mark})`);
      if (field.type === "date") return ["3i", "2i", "1i"].map((mark) => byName(part(mark))[0]);
      if (field.type === "radio" || field.type === "yesno") return [byName(field.name).find((box) => box.value === String(field.value))];
      if (field.type === "checkbox") return (field.value.length ? field.value : [null]).map((value) => byName(`${field.name}[]`).find((box) => box.value === value));
      return [byName(field.name)[0]];
    }
    if (field.type === "yesno") return [document.getElementById(`${field.id}_${field.value}`)];
    if (field.type === "date") return ["day", "month", "year"].map((part) => document.getElementById(`${field.id}-${part}`));
    return [document.getElementById(field.id)];
  };

  const HIDDEN = "[hidden], .govuk-radios__conditional--hidden, .govuk-checkboxes__conditional--hidden";
  const present = (field) => boxes(field).every((box) => box && box.isConnected && !box.closest(HIDDEN));
  const wanted = (field) => {
    if (field.type !== "date") return [String(field.value)];
    const [year, month, day] = String(field.value).split("-");
    return [String(Number(day)), String(Number(month)), year];
  };
  const group = (field) => byName(field.name !== undefined ? (field.type === "checkbox" ? `${field.name}[]` : field.name) : field.id);
  const holds = (field) => {
    if (field.type === "checkbox") return group(field).filter((box) => box.checked).map((box) => box.value).sort().join() === [...field.value].sort().join();
    if (field.type === "yesno" || field.type === "radio") return boxes(field)[0].checked;
    return boxes(field).every((box, i) => box.value === wanted(field)[i]);
  };
  const occupied = (field) => {
    if (field.type === "yesno" || field.type === "radio" || field.type === "checkbox") return group(field).some((box) => box.checked);
    return boxes(field).some((box) => box.value !== "");
  };
  const label = (field) => field.id ?? field.name;

  const type = (box, value) => {
    const owner = box instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    box.focus();
    Object.getOwnPropertyDescriptor(owner, "value").set.call(box, value);
    for (const name of ["input", "change"]) box.dispatchEvent(new Event(name, { bubbles: true }));
    box.dispatchEvent(new Event("blur"));
  };

  if (options.pageMustShow && !document.body.innerText.includes(options.pageMustShow)) {
    report.refused = `This page does not show "${options.pageMustShow}". Nothing was filled.`;
    return report;
  }
  const unknown = fields.filter((field) => !KINDS.includes(field.type));
  if (unknown.length) {
    report.refused = `The answers hold a kind of field this tool does not fill (${unknown[0].type}). Nothing was filled.`;
    return report;
  }
  const malformed = fields.filter((field) => field.type === "checkbox" && !(Array.isArray(field.value) && field.value.length));
  if (malformed.length) {
    report.refused = `The answers hold a tick-box question with nothing to tick (${label(malformed[0])}). Nothing was filled.`;
    return report;
  }

  const gone = fields.filter((field) => !field.conditional && !present(field));
  if (gone.length) {
    report.refused = `This page has changed: ${gone.map(label).join(", ")} not found. Nothing was filled. Use the answer sheet.`;
    return report;
  }

  for (const field of fields) {

    for (let waited = 0; field.conditional && !present(field) && waited < options.appearMs; waited += 50) await wait(50);
    if (!present(field)) {
      report.absent.push(label(field));
      continue;
    }
    if (holds(field)) {
      report.filled.push(label(field));
      continue;
    }
    if (occupied(field)) {
      report.left.push(label(field));
      continue;
    }

    if (field.type === "yesno" || field.type === "radio") boxes(field)[0].click();
    else if (field.type === "checkbox") boxes(field).forEach((box) => box && box.click());
    else boxes(field).forEach((box, i) => type(box, wanted(field)[i]));
    await wait(0);
    (present(field) && holds(field) ? report.filled : report.failed).push(label(field));
  }
  return report;
}
