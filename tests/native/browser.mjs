// Uses a synthetic PAM identity supplied over stdin by product.py. No API mocks.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
let raw = '';
for await (const chunk of process.stdin) raw += chunk;
const fixture = JSON.parse(raw); raw = '';
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium', args: ['--no-sandbox'] });
try {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 }, acceptDownloads: true });
  await context.route('**/*', route => new URL(route.request().url()).origin === fixture.base ? route.continue() : route.abort());
  const page = await context.newPage();
  await page.goto(fixture.base + '/#/files');
  const login = page.getByRole('dialog', { name: 'Owner sign in' });
  if (!(await login.isVisible())) await page.locator('#owner-account').click();
  await login.getByLabel('Username').fill(fixture.username);
  await login.getByLabel('Password').fill(fixture.password);
  fixture.password = '';
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(login).toHaveCount(0);
  await expect(page.locator('#owner-account')).toContainText('Sign out');
  await expect(page.getByRole('heading', { name: 'Private NAS', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'fixture.bin', exact: false })).toBeVisible();
  await page.getByLabel('Select fixture.bin', { exact: true }).check();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  const download = await downloaded;
  await download.saveAs(fixture.download);
  await page.getByRole('button', { name: 'New folder', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New folder', exact: true });
  await dialog.getByLabel('Name (no overwrite)').fill('browser-fixture');
  await dialog.getByRole('button', { name: 'New folder', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'browser-fixture', exact: false })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await mkdir('artifacts/native-browser', { recursive: true });
  await page.screenshot({ path: 'artifacts/native-browser/nas-mobile.png', fullPage: true });
  await page.locator('#menu').click();
  await page.locator('[data-route="permissions"]').click();
  await expect(page.getByRole('heading', { name: 'Permissions', exact: true })).toBeVisible();
  await expect.poll(() => page.locator('#sidebar').evaluate(node => node.getBoundingClientRect().right <= 1)).toBe(true);
  await page.locator('#theme').click();
  await page.getByRole('button', { name: 'Block', exact: true }).click();
  const rule = page.getByRole('dialog', { name: 'New permission rule' });
  await rule.getByLabel('Absolute target path').fill(fixture.nas);
  await rule.getByRole('button', { name: 'Save draft rule' }).click();
  async function applyDraft() {
    await page.getByRole('button', { name: 'Review impact', exact: true }).click();
    const review = page.getByRole('dialog', { name: 'Review permission impact' });
    await review.getByRole('button', { name: 'Apply changes', exact: true }).click();
    await expect(review).toContainText('Backend confirmed enforced revision');
    await review.getByRole('button', { name: 'Close', exact: true }).click();
  }
  await applyDraft();
  await expect(page.locator('[aria-label="Permission rules"]')).toContainText(fixture.nas);
  await page.screenshot({ path: 'artifacts/native-browser/permissions-mobile.png', fullPage: true });
  // Removing a discretionary Block must preserve the immutable private boundary.
  await page.locator('[aria-label="Permission rules"]').getByRole('button', { name: 'Remove', exact: true }).click();
  await applyDraft();
  await page.locator('#owner-account').click();
  await expect(page.locator('#owner-account')).toHaveText('Owner sign in');
  console.log(JSON.stringify({ result: 'passed', backend: 'real Rust/helper/PAM', viewport: '360x800', journeys: ['sign in', 'private NAS list', 'scoped download', 'mkdir', 'NAS Block review/apply/remove', 'sign out'] }));
} finally { await browser.close(); }
