import { test, expect } from '@playwright/test';

test('navigation, browser preferences, and app launch work end to end', async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await page.route('**/api/services', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      available: true,
      total: 4,
      services: [
        { name: 'active-demo.service', description: 'Active demo service', active: 'active', state: 'running' },
        { name: 'exited-demo.service', description: 'Exited demo service', active: 'active', state: 'exited' },
        { name: 'stopped-demo.service', description: 'Stopped demo service', active: 'inactive', state: 'dead' },
        { name: 'failed-demo.service', description: 'Failed demo service', active: 'failed', state: 'failed' },
      ],
    }),
  }));
  await page.route('**/api/vpn', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      available: true,
      connected: false,
      state: 'Needs owner setup',
      wireguard: { available: true, connected: false, state: 'Needs owner setup', peer_count: 0, listen_port: 51820 },
      tailscale: { available: true, connected: false, state: 'Disconnected' },
    }),
  }));
  await page.route('**/api/cockpit', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ available: true }),
  }));
  await page.route('**/api/private-service-ports', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ ports: [8765, 9090, 3080, 51821] }),
  }));

  await page.goto('/#/home');
  const brand = page.locator('.brand img');
  await expect(brand).toHaveAttribute('src', '/branding.png');
  await expect.poll(() => brand.evaluate(image => image.complete && image.naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator('.metric-card[data-metric="swap"]')).toContainText('Swap');
  await page.locator('#sidebar [data-route="system"]').click();
  await expect(page.locator('#page-system')).toContainText('Total active swap');
  await expect(page.locator('#page-system')).toContainText('Disk-backed swap');
  await expect(page.locator('#page-system')).toContainText('ZRAM device');
  await expect(page.locator('#page-system')).toContainText('actual memory occupied by compressed pages');
  await page.locator('#sidebar [data-route="home"]').click();
  const applicationLinkSetting = page.locator('#application-link-setting');
  await expect(applicationLinkSetting).toHaveValue('new-tab');
  const staticShortcut = page.locator('#wg-easy-link');
  await expect(staticShortcut).toHaveAttribute('target', '_blank');
  await expect(staticShortcut).toHaveAttribute('rel', 'noopener noreferrer');
  const routes = [
    ['home', 'Home'], ['apps', 'Applications'], ['system', 'System'],
    ['services', 'Services & Processes'], ['files', 'Files'], ['ssh', 'SSH'],
    ['network', 'Network & VPN'], ['storage', 'Storage'], ['settings', 'Settings'],
  ];
  for (const [route, title] of routes) {
    await page.locator(`#sidebar [data-route="${route}"]`).click();
    await expect(page.locator(`#page-${route}`)).toBeVisible();
    await expect(page.locator('[data-view]:visible')).toHaveCount(1);
    await expect(page.locator(`#page-${route} h1`)).toHaveText(title);
  }

  await page.locator('#sidebar [data-route="network"]').click();
  await expect(page.locator('#wireguard-listener')).toHaveText('51820/UDP');
  await expect(page.locator('#page-network')).toContainText("map the router's chosen external UDP port to the server listener shown above");
  await expect(page.locator('#page-network')).toContainText('This status cannot verify the router mapping.');
  await expect(page.locator('#wg-easy-link')).toHaveAttribute('href', 'http://127.0.0.1:51821/');

  await page.locator('#sidebar [data-route="services"]').click();
  await expect(page.locator('#cockpit-services-link')).toBeVisible();
  await expect(page.locator('#cockpit-services-link')).toHaveAttribute('href', 'http://127.0.0.1:9090/system/services');
  await expect(page.locator('#cockpit-process-link')).toBeVisible();
  await expect(page.locator('#cockpit-process-link')).toHaveAttribute('href', 'http://127.0.0.1:9090/system/terminal');
  await expect(page.locator('#service-total')).toHaveText('1 running · 1 exited · 1 inactive · 1 failed');
  const stoppedService = page.locator('#service-list .service-row').filter({ hasText: 'stopped-demo' });
  await expect(stoppedService).toBeHidden();
  await expect(page.locator('#service-list .service-row').filter({ hasText: 'failed-demo' })).toBeVisible();
  await page.locator('#search').fill('stopped-demo');
  await expect(stoppedService).toBeVisible();
  await page.locator('#search').fill('');
  const inactiveToggle = page.locator('#toggle-inactive-services');
  await inactiveToggle.click();
  await expect(stoppedService).toBeVisible();
  await expect(inactiveToggle).toHaveAttribute('aria-pressed', 'true');
  await inactiveToggle.click();
  await expect(stoppedService).toBeHidden();

  await page.setViewportSize({ width: 375, height: 812 });
  await expect.poll(() => page.locator('#sidebar').evaluate(sidebar => sidebar.getBoundingClientRect().right)).toBeLessThanOrEqual(0);
  const mobileBrand = page.locator('.mobile-brand');
  await expect(mobileBrand).toBeVisible();
  await expect.poll(() => mobileBrand.evaluate(image => image.complete && image.naturalWidth)).toBeGreaterThan(0);
  await page.locator('#menu').click();
  await expect(page.locator('#sidebar')).toHaveClass(/open/);
  await page.locator('#sidebar [data-route="settings"]').click();
  await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
  await applicationLinkSetting.selectOption('current');
  await expect(staticShortcut).not.toHaveAttribute('target', /.+/);
  await page.reload();
  await expect(applicationLinkSetting).toHaveValue('current');
  await expect(staticShortcut).not.toHaveAttribute('target', /.+/);
  await applicationLinkSetting.selectOption('new-tab');
  await expect(staticShortcut).toHaveAttribute('target', '_blank');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);

  const gpuSetting = page.locator('[data-metric-setting="gpu"]');
  await gpuSetting.uncheck();
  await page.locator('#refresh-interval').selectOption('15000');
  await page.locator('#theme-setting').selectOption('light');
  await expect(page.locator('.metric-card[data-metric="gpu"]')).toBeHidden();
  await page.reload();
  await expect(page.locator('[data-metric-setting="gpu"]')).not.toBeChecked();
  await expect(page.locator('#refresh-interval')).toHaveValue('15000');
  await expect(page.locator('#theme-setting')).toHaveValue('light');
  await page.locator('#metrics-reset').click();
  await expect(page.locator('.metric-card:not([hidden])')).toHaveCount(6);
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.locator('#app-form input[name="name"]').fill('Browser Acceptance App');
  await page.locator('#app-form input[name="url"]').fill(process.env.HUOU07_E2E_APP_URL);
  await page.locator('#app-form input[name="description"]').fill('Temporary local app used by browser acceptance tests.');
  await page.locator('#app-form input[name="health_url"]').fill(process.env.HUOU07_E2E_APP_HEALTH_URL);
  await page.locator('#app-save').click();
  await expect(page.locator('#app-registry-list .app-registry-row').filter({ hasText: 'Browser Acceptance App' })).toHaveCount(1);

  await page.locator('#sidebar [data-route="apps"]').click();
  const appCard = page.locator('.app-card').filter({ hasText: 'Browser Acceptance App' });
  await expect(appCard.locator('.app-state')).toHaveText(/Available/);
  await expect.poll(() => appCard.locator('.app-icon').evaluate(icon => icon.naturalWidth)).toBeGreaterThan(0);
  const appOpenLink = appCard.getByRole('link', { name: 'Open Browser Acceptance App' });
  await expect(appOpenLink).toHaveAttribute('target', '_blank');
  await page.locator('#sidebar [data-route="settings"]').click();
  await applicationLinkSetting.selectOption('current');
  await page.locator('#sidebar [data-route="apps"]').click();
  await expect(appOpenLink).not.toHaveAttribute('target', /.+/);
  await page.locator('#sidebar [data-route="settings"]').click();
  await applicationLinkSetting.selectOption('new-tab');
  await page.locator('#sidebar [data-route="apps"]').click();
  await expect(appOpenLink).toHaveAttribute('target', '_blank');
  const popupPromise = page.waitForEvent('popup');
  await appOpenLink.click();
  const popup = await popupPromise;
  await expect(popup.getByRole('heading', { name: 'Acceptance app launched' })).toBeVisible();
  await popup.close();

  await page.locator('#sidebar [data-route="settings"]').click();
  await page.locator('#app-form input[name="name"]').fill('Setup Acceptance App');
  await page.locator('#app-form input[name="url"]').fill(`${process.env.HUOU07_E2E_APP_URL}setup/1`);
  await page.locator('#app-form input[name="description"]').fill('Temporary application with a first-run setup wizard.');
  await page.locator('#app-form input[name="health_url"]').fill(`${process.env.HUOU07_E2E_APP_URL}setup-health`);
  await page.locator('#app-save').click();
  await page.locator('#sidebar [data-route="apps"]').click();
  const setupCard = page.locator('.app-card').filter({ hasText: 'Setup Acceptance App' });
  await expect(setupCard.locator('.app-state')).toHaveText('Owner setup required');
  const setupPopupPromise = page.waitForEvent('popup');
  await setupCard.getByRole('link', { name: 'Open Setup Acceptance App' }).click();
  const setupPopup = await setupPopupPromise;
  await expect(setupPopup.getByRole('heading', { name: 'Complete owner setup' })).toBeVisible();
  await setupPopup.close();

  await page.locator('#sidebar [data-route="settings"]').click();
  await page.locator('#app-form input[name="name"]').fill('Fallback Icon App');
  await page.locator('#app-form input[name="url"]').fill('https://not-used.example.invalid/');
  await page.locator('#app-save').click();
  await page.locator('#sidebar [data-route="apps"]').click();
  const fallbackCard = page.locator('.app-card').filter({ hasText: 'Fallback Icon App' });
  await expect.poll(() => fallbackCard.locator('.app-icon').evaluate(icon => icon.naturalWidth)).toBeGreaterThan(0);
  await expect(fallbackCard.locator('.app-mark')).toContainText('F');

  await page.locator('#sidebar [data-route="settings"]').click();
  const fallbackRow = page.locator('.app-registry-row').filter({ hasText: 'Fallback Icon App' });
  await fallbackRow.getByRole('button', { name: 'Remove' }).click();
  await expect(fallbackRow).toHaveCount(0);
  const appRow = page.locator('.app-registry-row').filter({ hasText: 'Browser Acceptance App' });
  await appRow.getByRole('button', { name: 'Remove' }).click();
  await expect(appRow).toHaveCount(0);
  const setupRow = page.locator('.app-registry-row').filter({ hasText: 'Setup Acceptance App' });
  await setupRow.getByRole('button', { name: 'Remove' }).click();
  await expect(setupRow).toHaveCount(0);
  await expect(pageErrors).toEqual([]);
  await expect(consoleErrors).toEqual([]);
});
