import { test, expect } from '@playwright/test';

// Synthetic browser contracts, distinct from Python/Rust API or OS acceptance.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const responses = {
      '/api/metrics': {
        supported: true, sampled_at: 1700000000,
        cpu: { usage_percent: 12, logical_cores: 4 },
        memory: { total: 8589934592, used: 2147483648, available: 6442450944, percent: 25 },
        storage: { total: 107374182400, used: 21474836480, free: 85899345920, percent: 20 },
        storage_devices: [], system: { hostname: 'synthetic-guest', os: 'Debian fixture' },
      },
      '/api/apps': { available: true, total: 0, apps: [] },
      '/api/processes': { available: true, total: 0, processes: [] },
      '/api/services': { available: true, total: 0, services: [] },
      '/api/cockpit': { available: false, reason: 'Synthetic service unavailable' },
      '/api/files': { available: false, installed: false, reason: 'Synthetic files unavailable' },
      '/api/vpn': { available: false, wireguard: { state: 'Unavailable' }, tailscale: { state: 'Unavailable' } },
      '/api/private-service-ports': { ports: [] },
    };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(responses[path] ?? {}) });
  });
});

test('360px keyboard navigation enters, cycles, closes and restores focus', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.setViewportSize({ width: 360, height: 812 });
  await page.goto('/#/home');
  const menu = page.getByRole('button', { name: 'Open navigation' });
  await expect(page.locator('#sidebar')).toHaveJSProperty('inert', true);
  await page.keyboard.press('Tab');
  await expect(menu).toBeFocused();
  await page.keyboard.press('Enter');
  const home = page.getByRole('link', { name: 'Home', exact: true });
  await expect(home).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('navigation', { name: 'Workspace pages' }).getByRole('link', { name: 'Settings' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(home).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('Enter');
  for (let i = 0; i < 7; i++) await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Storage', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Storage', exact: true })).toBeVisible();
  await expect(menu).toBeFocused();
  await expect(page.locator('#sidebar')).toHaveJSProperty('inert', true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  expect(errors).toEqual([]);
});

test('representative dark/light desktop and 360px states retain layout evidence', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  for (const width of [360, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/#/home');
    await expect(page.locator('#connection-label')).toHaveText('Connected');
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await testInfo.attach('home-dark-' + width, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  }
  await page.goto('/#/settings');
  const theme = page.getByRole('combobox', { name: 'Theme', exact: true });
  await expect(theme).toHaveAccessibleName('Theme');
  await theme.selectOption('light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await testInfo.attach('settings-light-desktop', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await page.goto('/#/files');
  await expect(page.locator('#file-manager-note')).toHaveText('Synthetic files unavailable');
  await expect(page.locator('#file-manager-link')).toBeHidden();
  await page.goto('/#/storage');
  await expect(page.getByRole('heading', { name: 'Storage', exact: true })).toBeVisible();
  await expect(page.locator('#storage-detail')).not.toHaveText('Waiting for system data');
  expect(errors).toEqual([]);
});

test('application save reports loading, error, retained input and retry success', async ({ page }) => {
  const errors = [];
  const consoleErrors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message); });
  let release;
  let attempts = 0;
  await page.route('**/api/apps', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    attempts++;
    if (attempts === 1) {
      await new Promise(resolve => { release = resolve; });
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Synthetic retryable failure' }) });
    }
    const body = route.request().postDataJSON();
    expect(body.app.name).toBe('Retry fixture');
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      available: true, total: 1, apps: [{ ...body.app, status: 'unavailable' }],
    }) });
  });
  await page.goto('/#/settings');
  await page.locator('#app-form input[name="name"]').fill('Retry fixture');
  await page.locator('#app-form input[name="url"]').fill('https://fixture.invalid/');
  const save = page.getByRole('button', { name: 'Add application', exact: true });
  const status = page.locator('#app-form-status');
  await expect(status).toHaveAttribute('role', 'status');
  await expect(status).toHaveAttribute('aria-live', 'polite');
  await save.click();
  await expect(status).toHaveText('Saving…');
  await expect(save).toBeDisabled();
  await expect.poll(() => typeof release).toBe('function');
  release();
  await expect(status).toHaveText('Synthetic retryable failure');
  await expect(page.locator('#app-form input[name="name"]')).toHaveValue('Retry fixture');
  await expect(save).toBeEnabled();
  await save.click();
  await expect(status).toHaveText('Saved.');
  await expect(page.locator('#app-registry-list')).toContainText('Retry fixture');
  expect(attempts).toBe(2);
  expect(errors).toEqual([]);
  // The single injected 503 is expected; all other browser errors fail the test.
  expect(consoleErrors.every(message => new URL(message.location().url).pathname === '/api/apps' && message.text().includes('503'))).toBe(true);
});
