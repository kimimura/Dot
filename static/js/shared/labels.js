import { esc } from "./dom.js";

export function stageLabel(s) {
  return { queued: "queued", converting: "converting", converted: "converted", rereading: "re-reading", identify: "waiting for you", pick: "choose a format", extracting: "reading", review: "review", revising: "revising", confirm_ops: "confirm?",
           save_ask: "save?", naming: "naming", pick_existing: "choose a profile", confirmed: "confirmed", failed: "failed", duplicate: "duplicate?" }[s] || s;
}

const SOURCES = { email: "Email", upload: "Upload", builder: "Profile Builder" };
const DONE = ["converted", "confirmed"];

// a file its format learns from is marked, and deleting or re-reading it says what is at stake
export function teachTag(d) {
  return d.teaches ? `<span class="teach-tag" title="${esc(d.profile_name)} learns from this file">learns from this</span>` : "";
}

export function deleteWarning(d) {
  if (!d.teaches) return "Delete this document and its files?";
  const others = d.teachers - 1;
  const lost = others > 0
    ? `${d.profile_name} still has ${others} other file${others === 1 ? "" : "s"} to learn from.`
    : `If you delete it, ${d.profile_name} will no longer recognise its PDFs, and emailed ${d.profile_name} files will be read by the model (uses tokens) until you confirm another one.`;
  return `${d.profile_name} learns from this file.\n\n${lost}\n\nDelete anyway?`;
}

export function rereadWarning(d) {
  if (!d.teaches) return null;
  return `${d.profile_name} learns from this sheet. Re-reading replaces it with a new read by the model (uses tokens); you can undo it afterwards.\n\nRe-read anyway?`;
}

// a finished file shows where it came in; one still in progress, or failed, shows how far it got
export function sourcePill(source, stage, sender) {
  const cls = DONE.includes(stage) ? "s-ok" : stage === "failed" ? "s-fail" : "s-held";
  const text = DONE.includes(stage) ? SOURCES[source] || "—" : stageLabel(stage);
  return `<span class="st ${cls}"${sender ? ` title="From ${esc(sender)}"` : ""}><span class="d"></span>${esc(text)}</span>`;
}
