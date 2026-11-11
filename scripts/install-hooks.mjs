// Installs the committed hooks without replacing an existing hook manager.
import { existsSync } from "node:fs";
import { execFileSync, spawnSync } from "node:child_process";
if (process.env.CI || process.env.VERCEL || !existsSync(".git")) process.exit(0);
const current = spawnSync("git", ["config", "--get", "core.hooksPath"], { encoding: "utf8" });
if (current.stdout.trim() && current.stdout.trim() !== ".githooks") {
  console.error("Existing core.hooksPath differs; integrate hooks manually before setup.");
  process.exit(1);
}
execFileSync("git", ["config", "core.hooksPath", ".githooks"], { stdio: "ignore" });
