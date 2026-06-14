import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  checkpointsForPhase,
  isIrreversibleAction,
  TWELVE_STEPS,
  TWELVE_TRADITIONS,
} from "./medallion-loop.js";
import { medallionCheckpointsFor } from "../security/approval-gate.js";
import { assertUrlAllowed } from "../security/url-allowlist.js";

describe("medallion loop", () => {
  it("has 12 steps and 12 traditions", () => {
    assert.equal(TWELVE_STEPS.length, 12);
    assert.equal(TWELVE_TRADITIONS.length, 12);
  });

  it("flags irreversible actions", () => {
    assert.equal(isIrreversibleAction("SAVE_ITCH_PROJECT"), true);
    assert.equal(isIrreversibleAction("navigate_itch_dashboard"), false);
  });

  it("pre_irreversible has more checkpoints than pre_action for SAVE", () => {
    const save = medallionCheckpointsFor("SAVE_ITCH_PROJECT");
    const nav = medallionCheckpointsFor("navigate_itch_dashboard");
    assert.ok(save.length > nav.length);
  });

  it("startup phase includes human authority tradition", () => {
    const cps = checkpointsForPhase("startup");
    assert.ok(cps.some((c) => c.kind === "tradition" && c.number === 2));
  });
});

describe("url allowlist", () => {
  it("allows itch and steam", () => {
    assert.doesNotThrow(() => assertUrlAllowed("https://itch.io/dashboard"));
    assert.doesNotThrow(() => assertUrlAllowed("https://partner.steamgames.com/"));
  });

  it("rejects unknown hosts", () => {
    assert.throws(() => assertUrlAllowed("https://evil.example/phish"), /allowlist/);
  });

  it("rejects non-https", () => {
    assert.throws(() => assertUrlAllowed("http://itch.io/"), /HTTPS/);
  });
});
