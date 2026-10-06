import { esc } from "./dom.js";

export function stageLabel(s) {
  return { queued: "queued", converting: "converting", converted: "converted", rereading: "re-reading", identify: "waiting for you", pick: "choose a format", extracting: "reading", review: "review", revising: "revising", confirm_ops: "confirm?",
           save_ask: "save?", naming: "naming", pick_existing: "choose a profile", confirmed: "confirmed", failed: "failed", duplicate: "duplicate?" }[s] || s;
}

const SOURCES = { email: "Email", upload: "Upload", builder: "Profile Builder" };
const DONE = ["converted", "confirmed"];

// a finished file shows where it came in; one still in progress, or failed, shows how far it got
export function sourcePill(source, stage, sender) {
  const cls = DONE.includes(stage) ? "s-ok" : stage === "failed" ? "s-fail" : "s-held";
  const text = DONE.includes(stage) ? SOURCES[source] || "—" : stageLabel(stage);
  return `<span class="st ${cls}"${sender ? ` title="From ${esc(sender)}"` : ""}><span class="d"></span>${esc(text)}</span>`;
}
