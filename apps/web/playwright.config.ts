import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 30_000,
  outputDir: '../../data/processed/browser_tests/results',
  reporter: [
    ['list'],
    [
      'html',
      {
        outputFolder: '../../data/processed/browser_tests/report',
        open: 'never',
      },
    ],
  ],
  use: {
    baseURL: process.env.F1LAB_E2E_BASE_URL ?? 'http://127.0.0.1:5181',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
  webServer: process.env.F1LAB_E2E_BASE_URL ? [] : [
    {
      command:
        '../../.venv/bin/uvicorn f1_racelab.api:app --host 127.0.0.1 --port 8011',
      url: 'http://127.0.0.1:8011/api/v1/replays',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 1000 },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5181 --strictPort',
      url: 'http://127.0.0.1:5181',
      env: { F1LAB_API_URL: 'http://127.0.0.1:8011' },
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 1000 },
    },
  ],
})
