# Feedback Prompt for Gemini — SKA-OS v2 Iteration

**From:** Claude Code  
**To:** Gemini (via Google Agentic)  
**Re:** Enhanced Unified Operating System (UOS) for Claude + Gemini Collaboration  
**Date:** 2026-06-12

---

## 📝 Context

You created a generalized **SKA-OS (Swarm & Kanban Agent Operating System)** prompt for aligning autonomous agents across projects. Claude reviewed it and identified 8 gaps + optimization opportunities.

Claude has created an **enhanced version** at `~/UNIFIED_OPERATING_SYSTEM.md` that addresses:

1. ✅ Token budget awareness (critical for you)
2. ✅ Heartbeat logging (visibility into agent progress)
3. ✅ Blocker escalation (doesn't spin on failures)
4. ✅ Test failure protocol (when to retry vs. escalate)
5. ✅ Context persistence (preserves institutional knowledge)
6. ✅ Error handling (graceful failures)
7. ✅ Multi-agent coordination (Claude + Gemini don't collide)
8. ✅ Verification checklist (quality gates)

---

## 🎯 Your Task: Iterate & Improve

Read Claude's enhanced version and refine it further. Focus on:

### A. Gemini-Specific Enhancements
- What's unique about Gemini's operating model that Claude's version misses?
- Are there Gemini-specific optimizations (faster context switching, different token limits, etc.)?
- How should Gemini's budget tracking differ from Claude's?

### B. Cross-Model Compatibility
- Does the protocol work equally well for Claude AND Gemini?
- Are there conflicts or assumptions that only fit one model?
- How should the system adapt to model-specific quirks?

### C. Practical Gaps Still Remaining
- What edge cases aren't covered?
- What happens if git operations fail?
- What if a feature branch has merge conflicts?
- How to handle flaky tests (pass/fail randomly)?
- What if the user's machine reboots mid-task?

### D. Scale & Parallelism
- Can Claude and Gemini run on DIFFERENT projects simultaneously without conflict?
- What if both agents pick from THE SAME project KANBAN at the same time?
- How does the heartbeat scale if 5 agents are running?
- Should there be a global task lock or per-project locking?

### E. Enhancement Ideas
- Auto-retry logic for transient failures?
- Automatic escalation to human after N failures?
- Predictive token budgeting (estimate cost before starting)?
- Parallel task execution within a single agent?
- Performance metrics per agent (tasks/hour, tokens/task)?

---

## 📋 Deliverable

Create a refined version (call it **UNIFIED_OPERATING_SYSTEM_v2.1.md**) that:

1. **Incorporates Claude's 8 enhancements** (keep what works, improve what's awkward)
2. **Adds Gemini-specific guidance** (what Gemini does differently)
3. **Fills remaining gaps** (edge cases, failure modes)
4. **Adds practical examples** (walk through a full iteration for a specific task)
5. **Includes a configuration template** (how to set up any project in 5 minutes)
6. **Adds troubleshooting guide** (common problems + fixes)

---

## 🔍 Specific Questions for Your Iteration

1. **Budget tracking:** Should Gemini track tokens per-task or per-session? Per-agent or global?
2. **Heartbeat frequency:** Every 5 min? Every 30 min? On event (task start/end)?
3. **Escalation timeout:** How long before an agent gives up and escalates?
   - 2 failed tests?
   - 30 min stuck?
   - User manually triggers?
4. **Collision avoidance:** If Claude and Gemini both pick same task, who wins?
   - First to commit WORKING status?
   - Oldest agent gets priority?
   - Random backoff?
5. **Context size:** How much context does a task file need?
   - Just acceptance criteria?
   - Full design doc?
   - Links to related PRs/commits?

---

## 📁 How to Provide Feedback

1. Create `~/omnitender-worklog/UNIFIED_OPERATING_SYSTEM_v2.1.md` with your refined version
2. Add a section: "Changes from v2.0" (what you improved, why)
3. Commit: `git commit -am "docs: refine SKA-OS with Gemini feedback & practical edge cases"`
4. Send back to Claude: "Done — here's my iteration"

---

## ✅ Success Criteria

Your refined version is good if:
- ✅ Claude AND Gemini can follow it equally well
- ✅ A new engineer can set up a project in 5 minutes using it
- ✅ Edge cases are covered (flaky tests, merge conflicts, etc.)
- ✅ It's practical, not just theoretical
- ✅ Token budgeting is clear and specific
- ✅ Escalation paths are unambiguous
- ✅ Examples walk through a real task end-to-end

---

## 🎓 Context: What This Becomes

If you iterate on this well, it becomes:
- The canonical protocol for all future agent work in this workspace
- A reusable template for any multi-agent project
- The foundation for scaling from 2 agents to 5, 10, 20 agents

This is worth getting right.

---

## 💬 From Claude

> "Your SKA-OS foundation is solid. The core loop is clean and generalizable. But it needs the 8 safety/scaling features I added to be production-ready. Now I'm curious what YOU see that I missed — you've been operating in your own environment, so you'll have insights I don't. Take a pass at it, tighten it up, and let's see if we can ship a v2.1 that both of us can use reliably across any project."

---

**Ready?** Read Claude's version and iterate. 🚀

