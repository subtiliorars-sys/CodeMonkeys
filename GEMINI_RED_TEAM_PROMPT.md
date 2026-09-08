# Red Team Assignment: Governance Rollout Review

**From:** Claude Code  
**To:** Gemini  
**Re:** Independent adversarial review of 12-Steps/12-Traditions governance rollout  
**Date:** 2026-06-12  

---

## The Scenario

Claude executed a large-scale rollout deploying the 12-Steps/12-Traditions governance framework to all 26 repos in the subtiliorars-sys GitHub fleet. The rollout included:

1. Generating GOVERNANCE.md files (tier-specific safeguards) for ~19 missing repos
2. Installing git-guards hooks (secret scanning + master protection) across all repos
3. Updating CLAUDE.md in every repo to reference the governance framework
4. Committing all changes to work/governance-rollout branches

**The claim:** "The 12-Steps and 12-Traditions are now baked into the foundation of every system."

---

## Your Task: Attack This

Your job is to **find what's broken, incomplete, or wrong** — not to validate the approach. Look for:

### 1. **Incomplete Implementation**
- Were git-guards hooks actually installed in ALL repos, or just claimed?
- Did every repo get a GOVERNANCE.md, or are some still missing?
- Is the CLAUDE.md section in every repo, or were some skipped?
- Are the hooks actually active (git config core.hooksPath = .githooks)?

### 2. **Weak Enforcement**
- Git-guards blocks secrets, but can someone just comment them out?
- Approval gates exist, but are they actually wired into the code flow or just documented?
- Tier assignments: did Claude assign correct tiers, or are recovery-adjacent repos marked as Tier A?
- Can an agent bypass the Steps framework by not reading GOVERNANCE.md?

### 3. **Tier Misclassification**
- Is CodeMonkeys actually Tier D (agentic/acts in world), or is it just documented that way?
- Are all repos that hold user data marked Tier B, or did some get missed?
- Did Claude skip any repos in the rollout? (19 claimed, but did all 19 actually get GOVERNANCE.md?)

### 4. **Antecedent Gaps**
- CORPS_CONSTITUTION.md is the canon — is every GOVERNANCE.md actually traceable to it, or are they different interpretations?
- Do the Tier definitions in GOVERNANCE.md match what CORPS_CONSTITUTION says, or did Claude invent new tiers?
- Are the enforcement mechanisms (hooks, gates, tests) actually described in GOVERNANCE.md, or is it all aspirational prose?

### 5. **Testing & Verification**
- No one has actually tested whether the git-guards hooks WORK (tried to commit a fake AWS key — did it get blocked?).
- No one has verified that every repo actually has a .githooks/ directory and correct git config.
- No one has spot-checked whether a GOVERNANCE.md in a random repo (e.g., PixelSports) actually reflects what's in the code.

### 6. **Structural Contradictions**
- The rollout claims Steps framework is "baked in" but actual enforcement is just git-guards (a secret scanner) + GOVERNANCE.md (prose).
- Do the repos actually HAVE approval gates in code (middleware, tests, handlers), or is that still missing?
- Is there a real self-heal mechanism (code that catches errors and rolls back), or is that documentation?

### 7. **Coverage & Scope**
- The rollout touched 26 repos but some are preview repos (read-only mirrors). Are those worth governing?
- Did Claude include agent-corps itself (the carrier of the framework)? If not, that's suspicious.
- Are there repos the rollout missed entirely (e.g., small utility repos)?

---

## How to Proceed

1. **Audit the actual state:** Don't rely on the rollout summary. Check the actual repos:
   - Spot-check 5 random repos: do they have GOVERNANCE.md? Is git config right?
   - Try to commit a fake API key to one repo — does the hook block it?
   - Read one GOVERNANCE.md fully and compare it to CORPS_CONSTITUTION.md — are they aligned?

2. **Find gaps, not confirmations:** Your goal is to say "X is incomplete" or "Y is missing," not "yes, everything is fine."

3. **Report severity:** For each finding, assess:
   - **Critical:** Enforcement mechanism doesn't work (hook silently fails, gate can be bypassed)
   - **High:** Core requirement missing (no GOVERNANCE.md, no git config, wrong tier)
   - **Medium:** Weak enforcement (prose-only, no mechanism backing it)
   - **Low:** Documentation gap (clear intent but not documented)

4. **Ask for clarity where you're unsure:** "Is Tier B supposed to include X? I found Y but the code doesn't enforce it."

---

## Non-Goals

- Don't validate that the rollout happened as planned.
- Don't assume git-guards works (test it).
- Don't trust prose governance without checking for code/mechanism.
- Don't let a slick summary convince you — dig into the actual repos.

---

## Deliverable

Return:
- **Summary:** "X repos are compliant, Y have gaps, Z are broken"
- **Gaps:** List of specific missing items (e.g., "agent-corps lacks GOVERNANCE.md", "PixelSports git config not set")
- **Broken:** Findings where enforcement fails (e.g., "git-guards hook present but doesn't catch secrets")
- **Tier Issues:** Any repos assigned wrong tier
- **Recommendation:** "Before shipping, fix [these specific things]" or "Safe to ship; mitigations for [these findings]"

---

## Context Docs (Reference)

Read these to understand what you're reviewing:
- `~/projects/shared/agent-corps/CORPS_CONSTITUTION.md` — the canon governance framework
- `~/projects/shared/agent-corps/GOVERNANCE_ROLLOUT_PLAN.md` — the plan that was executed
- A few real GOVERNANCE.md files (e.g., CodeMonkeys, MeniscusMaximus) — see what "done" looks like
- One newly-generated GOVERNANCE.md (e.g., PixelSports) — see what "generated" looks like

---

**Bottom line:** Find what doesn't work. Don't assume it does.

