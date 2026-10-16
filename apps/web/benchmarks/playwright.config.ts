import { defineConfig } from '@playwright/test'

// Deliberately separate from the correctness suite: opt in with benchmark:replay.
export default defineConfig({
  testDir: '.',
  testMatch: 'replay-performance.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 45_000,
  outputDir: '../../../data/processed/browser_benchmarks/results',
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5182',
    browserName: 'chromium',
    viewport: { width: 1440, height: 1000 },
    headless: true,
    trace: 'off',
    screenshot: 'off',
  },
  webServer: [
    {
      cwd: '..',
      command: '../../.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8012',
      url: 'http://127.0.0.1:8012/api/v1/replays',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 1000 },
    },
    {
      cwd: '..',
      command: 'npm run dev -- --host 127.0.0.1 --port 5182 --strictPort',
      url: 'http://127.0.0.1:5182',
      env: { F1LAB_API_URL: 'http://127.0.0.1:8012' },
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 1000 },
    },
  ],
})
