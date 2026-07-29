import { readFileSync } from "node:fs";

export const PUBLIC_ENV_KEYS = Object.freeze([
  "NEXT_PUBLIC_ODM_WS_URL",
  "NEXT_PUBLIC_ODM_AVATAR_URL",
  "NEXT_PUBLIC_ODM_RENDER_PRESET",
]);

export function parseEnv(text) {
  const values = {};

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const match = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!match) {
      continue;
    }

    const [, key, rawValue] = match;
    let value = rawValue.trim();
    const quoted =
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")));

    if (quoted) {
      value = value.slice(1, -1);
    } else {
      value = value.replace(/\s+#.*$/, "").trimEnd();
    }
    values[key] = value;
  }

  return values;
}

/**
 * Load the repo-root `.env` without exposing server-only configuration to
 * Next.js. Existing process variables win, matching common deployment
 * expectations.
 */
export function loadPublicEnv(filePath, target = process.env) {
  let values;
  try {
    values = parseEnv(readFileSync(filePath, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      return [];
    }
    throw error;
  }

  const loaded = [];
  for (const key of PUBLIC_ENV_KEYS) {
    if (target[key] === undefined && Object.hasOwn(values, key)) {
      target[key] = values[key];
      loaded.push(key);
    }
  }
  return loaded;
}
