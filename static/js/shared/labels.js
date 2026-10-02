import { esc } from "./dom.js";

export function stageLabel(s) {
  return { queued: "queued", converting: "converting", converted: "converted", rereading: "re-reading", identify: "waiting for you", pick: "choose a format", extracting: "reading", review: "review", revising: "revising", confirm_ops: "confirm?",
           save_ask: "save?", naming: "naming", pick_existing: "choose a profile", confirmed: "confirmed", failed: "failed", duplicate: "duplicate?" }[s] || s;
}

export function statusPill(stage) {
  const cls = stage === "confirmed" || stage === "converted" ? "s-ok" : stage === "failed" ? "s-fail" : "s-held";
  return `<span class="st ${cls}"><span class="d"></span>${esc(stage === "confirmed" ? "confirmed" : stageLabel(stage))}</span>`;
}
