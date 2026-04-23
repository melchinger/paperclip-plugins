import { mkdir, copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const distDir = resolve(rootDir, "dist");

await mkdir(distDir, { recursive: true });
await copyFile(resolve(rootDir, "src/manifest.js"), resolve(distDir, "manifest.js"));
await copyFile(resolve(rootDir, "src/worker.js"), resolve(distDir, "worker-bootstrap.js"));
await mkdir(resolve(distDir, "ui"), { recursive: true });
await copyFile(resolve(rootDir, "src/ui/index.js"), resolve(distDir, "ui/index.js"));
