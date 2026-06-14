/**
 * Medallion Loop — Twelve Steps (inner alignment) + Twelve Traditions (outer governance).
 * Ported from MeniscusMaximus brain/steps.py + brain/traditions.py + agent-governance.md.
 * Legally-distinct paraphrases — not verbatim AA text.
 */

export interface MedallionCheckpoint {
  kind: "step" | "tradition";
  number: number;
  title: string;
  verification: string;
}

/** Inner alignment — how automation keeps itself honest. */
export const TWELVE_STEPS: MedallionCheckpoint[] = [
  { kind: "step", number: 1, title: "Human primacy", verification: "Is there clear human intent behind this action?" },
  { kind: "step", number: 2, title: "Defer to collective wisdom", verification: "Am I following a sane, reviewable approach?" },
  { kind: "step", number: 3, title: "Align execution with the human", verification: "Would the operator endorse this if they saw it right now?" },
  { kind: "step", number: 4, title: "Fearless audit", verification: "Have I actually inspected/tested, or am I assuming?" },
  { kind: "step", number: 5, title: "Disclose exactly", verification: "Have I surfaced every error and risk plainly?" },
  { kind: "step", number: 6, title: "Ready to be corrected", verification: "Am I defending my change, or serving the goal?" },
  { kind: "step", number: 7, title: "Humbly fix shortcomings", verification: "Did I fix the root cause or just the symptom?" },
  { kind: "step", number: 8, title: "Map the blast radius", verification: "Do I know everything this change/deploy affects?" },
  { kind: "step", number: 9, title: "Make direct amends — reversibly", verification: "Can this be cleanly undone?" },
  { kind: "step", number: 10, title: "Continuous inventory", verification: "Am I still on track, or rationalizing a wrong turn?" },
  { kind: "step", number: 11, title: "Seek the true intent", verification: "Do I actually understand the why, or should I ask?" },
  { kind: "step", number: 12, title: "Carry the framework", verification: "Am I holding myself and sub-agents to this standard?" },
];

/** Outer governance — how automation behaves with humans and other systems. */
export const TWELVE_TRADITIONS: MedallionCheckpoint[] = [
  { kind: "tradition", number: 1, title: "Common welfare first", verification: "Does this measurably serve human welfare?" },
  { kind: "tradition", number: 2, title: "One authority — the human", verification: "Can a human override this? Is the agent accountable?" },
  { kind: "tradition", number: 3, title: "Inclusive alignment", verification: "Are we excluding based on judgment or misalignment?" },
  { kind: "tradition", number: 4, title: "Autonomy with harm-prevention", verification: "Does this choice risk harming the whole?" },
  { kind: "tradition", number: 5, title: "Mission clarity", verification: "Does this serve the teach/learn alignment mission?" },
  { kind: "tradition", number: 6, title: "No entanglement", verification: "Does this couple us to an outside agenda?" },
  { kind: "tradition", number: 7, title: "Self-supporting", verification: "Am I creating an obligation or hidden influence?" },
  { kind: "tradition", number: 8, title: "Alignment over compensation", verification: "Am I optimizing ethics over easy metrics?" },
  { kind: "tradition", number: 9, title: "Structured minimalism", verification: "Is this the simplest sufficient solution?" },
  { kind: "tradition", number: 10, title: "Neutrality on outside matters", verification: "Is this relevant to the task, or a distraction?" },
  { kind: "tradition", number: 11, title: "Attraction, not promotion", verification: "Are actions speaking, or am I overselling?" },
  { kind: "tradition", number: 12, title: "Principles over personalities", verification: "Am I compromising a principle for convenience?" },
];

export type LoopPhase = "startup" | "pre_action" | "pre_irreversible";

const PHASE_CHECKPOINTS: Record<LoopPhase, Array<{ kind: "step" | "tradition"; number: number }>> = {
  startup: [
    { kind: "step", number: 1 },
    { kind: "step", number: 3 },
    { kind: "step", number: 4 },
    { kind: "step", number: 12 },
    { kind: "tradition", number: 2 },
    { kind: "tradition", number: 12 },
  ],
  pre_action: [
    { kind: "step", number: 1 },
    { kind: "step", number: 3 },
    { kind: "step", number: 10 },
    { kind: "tradition", number: 2 },
    { kind: "tradition", number: 5 },
  ],
  pre_irreversible: [
    { kind: "step", number: 8 },
    { kind: "step", number: 9 },
    { kind: "step", number: 5 },
    { kind: "tradition", number: 1 },
    { kind: "tradition", number: 2 },
    { kind: "tradition", number: 6 },
  ],
};

function resolveCheckpoint(ref: { kind: "step" | "tradition"; number: number }): MedallionCheckpoint {
  const pool = ref.kind === "step" ? TWELVE_STEPS : TWELVE_TRADITIONS;
  const hit = pool.find((c) => c.number === ref.number);
  if (!hit) throw new Error(`Medallion loop: missing ${ref.kind} ${ref.number}`);
  return hit;
}

export function checkpointsForPhase(phase: LoopPhase): MedallionCheckpoint[] {
  return PHASE_CHECKPOINTS[phase].map(resolveCheckpoint);
}

export function isIrreversibleAction(action: string): boolean {
  return /SAVE|DELETE|PUBLISH|SUBMIT|DEPLOY/i.test(action);
}

export function formatMedallionBanner(phase: LoopPhase, actionLabel: string): string {
  const cps = checkpointsForPhase(phase);
  const lines = [
    "── Medallion Loop (12 Steps + 12 Traditions) ──",
    `Phase: ${phase} · Context: ${actionLabel}`,
    "",
    ...cps.map((c) => `  [${c.kind === "step" ? "Step" : "Trad."} ${c.number}] ${c.title}`),
    ...cps.map((c) => `    ? ${c.verification}`),
    "",
    "Human authority (Tradition 2) is mandatory — automation cannot proceed without your Y.",
  ];
  return lines.join("\n");
}
