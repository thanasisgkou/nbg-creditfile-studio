import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
const port = process.env.STUDIO_TEST_PORT || "8521";
const python = resolve(
  "../.venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    viewport: { width: 1366, height: 900 },
    screenshot: "only-on-failure",
  },
  reporter: [["list"]],
  webServer: {
    command: `"${python}" ../tests/run_browser_server.py`,
    url: `http://127.0.0.1:${port}/api/v1/health`,
    reuseExistingServer: false,
    timeout: 60000,
  },
});
