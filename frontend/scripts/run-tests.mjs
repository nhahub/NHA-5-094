import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tempRoot = resolve(frontendRoot, ".vitest-tmp");
mkdirSync(tempRoot, { recursive: true });

const result = spawnSync(
  process.execPath,
  [resolve(frontendRoot, "node_modules/vitest/vitest.mjs"), "run", ...process.argv.slice(2)],
  {
    cwd: frontendRoot,
    env: { ...process.env, TEMP: tempRoot, TMP: tempRoot, TMPDIR: tempRoot },
    stdio: "inherit",
  },
);

if (result.error) {
  process.stderr.write(`${result.error.message}\n`);
}
process.exit(result.status ?? 1);
