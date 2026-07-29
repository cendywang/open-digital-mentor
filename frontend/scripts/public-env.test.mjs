import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { loadPublicEnv, parseEnv } from "./public-env.mjs";

test("parseEnv handles comments, export syntax and quoted values", () => {
  assert.deepEqual(
    parseEnv(`
      # comment
      export NEXT_PUBLIC_ODM_WS_URL = "ws://localhost:9000/ws"
      NEXT_PUBLIC_ODM_RENDER_PRESET=stylized # local default
      INVALID LINE
    `),
    {
      NEXT_PUBLIC_ODM_WS_URL: "ws://localhost:9000/ws",
      NEXT_PUBLIC_ODM_RENDER_PRESET: "stylized",
    },
  );
});

test("loadPublicEnv allowlists public keys and preserves explicit variables", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "odm-public-env-"));
  const envFile = path.join(directory, ".env");
  writeFileSync(
    envFile,
    [
      "NEXT_PUBLIC_ODM_WS_URL=ws://from-file/ws",
      "NEXT_PUBLIC_ODM_AVATAR_URL=/avatars/custom.vrm",
      "ODM_LLM_API_KEY=must-not-leak",
    ].join("\n"),
  );

  try {
    const target = { NEXT_PUBLIC_ODM_WS_URL: "ws://explicit/ws" };
    const loaded = loadPublicEnv(envFile, target);

    assert.deepEqual(loaded, ["NEXT_PUBLIC_ODM_AVATAR_URL"]);
    assert.deepEqual(target, {
      NEXT_PUBLIC_ODM_WS_URL: "ws://explicit/ws",
      NEXT_PUBLIC_ODM_AVATAR_URL: "/avatars/custom.vrm",
    });
    assert.equal(target.ODM_LLM_API_KEY, undefined);
  } finally {
    rmSync(directory, { recursive: true });
  }
});

test("loadPublicEnv treats a missing optional file as empty", () => {
  assert.deepEqual(loadPublicEnv("/path/that/does/not/exist", {}), []);
});
