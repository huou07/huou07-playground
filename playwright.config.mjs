import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: process.env.HUOU07_E2E_BACKEND === 'rust'
    ? ['ux.spec.mjs', 'rust-static.spec.mjs']
    : ['dashboard.spec.mjs', 'ux.spec.mjs'],
  timeout: 45000,
  expect: { timeout: 8000 },
  outputDir: 'test-results',
  workers: 1,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL: process.env.HUOU07_E2E_BASE_URL,
    browserName: 'chromium',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {},
  },
});
