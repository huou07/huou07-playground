import { test, expect } from '@playwright/test';

// Browser interaction contracts use synthetic responses; they do not prove OS isolation.
async function fixture(page, { authenticated = true, entries = [], failList = false } = {}) {
  const calls = [], files = [...entries];
  let signedIn = authenticated, listFailure = failList;
  let policy = { revision: 3, enforced_revision: 3, preset: 'none', workspace: '/fixtures', workers: [{ name: 'worker-a', state: 'running', preset: 'none' }], rules: [], approvals: [], audit: [], capabilities: { mechanism: 'acl', independent_directory_rights: false } };
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    let body; try { body = request.postDataJSON(); } catch {}
    calls.push({ path, method: request.method(), body, headers: request.headers(), url });
    let response = {}, status = 200;
    if (path === '/api/owner/session') response = { authenticated: signedIn, username: signedIn ? 'fixture-owner' : undefined, csrf: signedIn ? 'fixture-csrf' : undefined };
    else if (path === '/api/owner/login') { signedIn = true; response = { ok: true }; }
    else if (path === '/api/owner/logout') { signedIn = false; response = { ok: true }; }
    else if (path === '/api/control/status') response = policy;
    else if (path === '/api/control/dry-run') response = { ok: true, impact: { restart_workers: ['worker-a'], grants: [], revocations: [ '/fixtures/private' ] } };
    else if (path === '/api/control/apply') {
      if (body.expected_revision !== policy.revision) { status = 409; response = { error: 'Stale revision. Refresh and retry.' }; }
      else { policy = { ...policy, ...body, revision: 4, enforced_revision: 4 }; response = { ok: true, revision: 4, enforced_revision: 4 }; }
    } else if (path === '/api/control/scan') response = { findings: [{ path: '/fixtures/.env', reason: 'credential filename', confidence: 'high' }, { path: '/fixtures/readme.md', reason: 'No known sensitive marker', confidence: 'medium' }], skipped: [{ path: '/fixtures/unreadable', reason: 'Permission denied' }], partial: true };
    else if (path === '/api/fs/list') {
      if (listFailure) { listFailure = false; status = 403; response = { error: 'Permission denied for fixture path' }; }
      else response = { path: url.searchParams.get('path'), parent: '/', private: url.searchParams.get('area') === 'nas', entries: files, total: files.length, capacity: { total: 10737418240, used: 2147483648, free: 8589934592, available: 7516192768 } };
    } else if (path === '/api/fs/mutate') {
      if (body.action === 'mkdir') files.push({ name: body.path.split('/').at(-1), path: body.path, kind: 'directory' });
      if (body.action === 'rename') { const entry = files.find(item => item.path === body.path); if (entry) { entry.path = body.destination; entry.name = body.destination.split('/').at(-1); } }
      if (body.action === 'delete') { const index = files.findIndex(item => item.path === body.path); if (index >= 0) files.splice(index, 1); }
      response = { ok: true };
    } else if (path === '/api/fs/preview') {
      return route.fulfill({ contentType: 'text/plain', body: '<img src=x onerror="window.fixtureExecuted=true"> fixture text' });
    } else if (path === '/api/fs/upload') response = { ok: true };
    else if (path === '/api/metrics') response = { supported: true, sampled_at: 1700000000, cpu: { usage_percent: 12, logical_cores: 4 }, memory: { total: 8589934592, used: 2147483648, available: 6442450944, percent: 25 }, storage: { total: 107374182400, used: 21474836480, free: 85899345920, percent: 20 }, storage_devices: [], system: { hostname: 'fixture', os: 'Debian fixture' } };
    else if (path === '/api/apps') response = { available: true, total: 0, apps: [] };
    else if (path === '/api/processes') response = { available: true, total: 0, processes: [] };
    else if (path === '/api/services') response = { available: true, total: 0, services: [] };
    else if (path === '/api/files') response = { available: false, installed: false, reason: 'Legacy integration not configured' };
    else if (path === '/api/vpn') response = { available: false, wireguard: { state: 'Unavailable' }, tailscale: { state: 'Unavailable' } };
    else if (path === '/api/private-service-ports') response = { ports: [] };
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(response) });
  });
  return { calls, setPolicy: next => { policy = next; }, getPolicy: () => policy };
}

test('owner login keeps credentials out of storage and logout clears private browser data', async ({ page }) => {
  const { calls } = await fixture(page, { authenticated: false, entries: [{ name: 'private.txt', path: '/private.txt', kind: 'file', size: 12 }] });
  await page.goto('/#/files');
  const login = page.getByRole('dialog', { name: 'Owner sign in' });
  await expect(login).toBeVisible();
  await login.getByLabel('Username').fill('fixture-owner');
  await login.getByLabel('Password').fill('synthetic-password');
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('button', { name: 'private.txt', exact: true })).toBeVisible();
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toMatch(/fixture-csrf|synthetic-password/);
  await page.getByRole('button', { name: 'fixture-owner · Sign out' }).click();
  await expect(page.getByRole('button', { name: 'private.txt', exact: true })).toHaveCount(0);
  expect(calls.find(call => call.path === '/api/owner/logout').headers['x-h07p-csrf']).toBe('fixture-csrf');
});

test('permission drafts require dry-run and explicit apply; backend confirmation controls enforced status', async ({ page }) => {
  const { calls } = await fixture(page);
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#/permissions');
  await expect(page.getByText('Desired revision 3 · Enforced revision 3', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Block', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'New permission rule' });
  await editor.getByLabel('Absolute target path').fill('/fixtures/private');
  await editor.getByRole('button', { name: 'Save draft rule' }).click();
  await expect(page.getByText('/fixtures/private', { exact: true })).toBeVisible();
  expect(calls.filter(call => call.path === '/api/control/apply')).toHaveLength(0);
  await page.getByRole('button', { name: 'Review impact', exact: true }).click();
  const review = page.getByRole('dialog', { name: 'Review permission impact' });
  await expect(review.getByText(/stop tasks and restart these workers/)).toBeVisible();
  await review.getByRole('button', { name: 'Apply changes' }).click();
  await expect(review.getByRole('status')).toHaveText('Backend confirmed enforced revision 4.');
  const apply = calls.find(call => call.path === '/api/control/apply');
  expect(apply.body).toMatchObject({ expected_revision: 3, preset: 'none', rules: [{ target: '/fixtures/private', action: 'block' }] });
  expect(apply.headers['x-h07p-csrf']).toBe('fixture-csrf');
  expect(errors).toEqual([]);
});

test('metadata scan is partial, starts unselected and only selected candidates enter the draft', async ({ page }) => {
  const { calls } = await fixture(page);
  await page.goto('/#/permissions');
  await page.getByRole('button', { name: 'Auto Detect', exact: true }).click();
  const scan = page.getByRole('dialog', { name: 'Auto Detect · review suggestions' });
  await scan.getByRole('button', { name: 'Start scan' }).click();
  await expect(scan.getByRole('status')).toContainText('Partial scan');
  await expect(scan.getByRole('button', { name: 'Review selected' })).toBeDisabled();
  await scan.getByLabel('/fixtures/.env', { exact: true }).check();
  await scan.getByRole('button', { name: 'Review selected' }).click();
  await page.getByRole('dialog', { name: 'Review 1 selected suggestions' }).getByRole('button', { name: 'Add selected to draft' }).click();
  await expect(page.getByLabel('Permission rules').getByText('/fixtures/.env', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Permission rules').getByText('/fixtures/readme.md', { exact: true })).toHaveCount(0);
  expect(calls.find(call => call.path === '/api/control/scan').body.content).toBe(false);
  expect(calls.filter(call => call.path === '/api/control/apply')).toHaveLength(0);
});

test('NAS safely previews text, downloads active formats and requires permanent-delete confirmation', async ({ page }) => {
  const { calls } = await fixture(page, { entries: [{ name: 'note.txt', path: '/note.txt', kind: 'file', size: 50 }, { name: 'active.svg', path: '/active.svg', kind: 'file', size: 30 }] });
  await page.goto('/#/files');
  await page.getByRole('button', { name: 'note.txt', exact: true }).click();
  const preview = page.getByRole('dialog', { name: 'note.txt' });
  await expect(preview.locator('pre')).toContainText('<img src=x onerror=');
  expect(await page.evaluate(() => window.fixtureExecuted)).toBeUndefined();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'note.txt', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'active.svg', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('status')).toContainText('download only');
  expect(calls.filter(call => call.path === '/api/fs/preview')).toHaveLength(1);
  await page.keyboard.press('Escape');
  await page.getByLabel('Select note.txt', { exact: true }).check();
  await page.locator('#nas-browser').getByRole('button', { name: 'Delete', exact: true }).click();
  expect(calls.filter(call => call.body?.action === 'delete')).toHaveLength(0);
  await page.getByRole('button', { name: 'Permanently delete', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('status')).toContainText('note.txt: deleted');
  expect(calls.find(call => call.body?.action === 'delete').body.confirmed).toBe(true);
  expect(calls.find(call => call.body?.action === 'delete').headers['x-h07p-csrf']).toBe('fixture-csrf');
});

test('host errors retry and desktop/mobile themes retain usable layout', async ({ page }, testInfo) => {
  await fixture(page, { failList: true, entries: [{ name: 'ordinary-file-with-long-name.txt', path: '/ordinary-file-with-long-name.txt', kind: 'file', size: 4 }] });
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/#/storage');
  const browser=page.locator('#host-browser');
  await expect(browser.getByRole('status').first()).toContainText('Permission denied');
  await browser.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(browser.getByText('7.00 GiB')).toBeVisible();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const width of [1440, 360]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ['dark', 'light']) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      const screenshot = testInfo.outputPath('storage-' + theme + '-' + width + '.png');
      await page.screenshot({ fullPage: true, path: screenshot, animations: 'disabled' });
      await testInfo.attach('storage-' + theme + '-' + width, { path: screenshot, contentType: 'image/png' });
    }
  }
  await page.goto('/#/permissions');
  await expect(page.getByRole('button', { name: 'Review impact', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  const screenshot = testInfo.outputPath('permissions-light-360.png');
  await page.screenshot({ fullPage: true, path: screenshot, animations: 'disabled' });
  await testInfo.attach('permissions-light-360', { path: screenshot, contentType: 'image/png' });
  expect(errors).toEqual([]);
});

test('refreshing server status preserves a draft base revision and stale apply retains inputs', async ({ page }) => {
  const state = await fixture(page);
  await page.goto('/#/permissions');
  await page.getByRole('button', { name: 'Block', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'New permission rule' });
  await editor.getByLabel('Absolute target path').fill('/fixtures/preserve-me');
  await editor.getByRole('button', { name: 'Save draft rule' }).click();
  state.setPolicy({ ...state.getPolicy(), revision: 7, enforced_revision: 7 });
  await page.goto('/#/home');
  await page.goto('/#/permissions');
  await expect(page.getByText(/Desired revision 7/)).toBeVisible();
  await page.getByRole('button', { name: 'Review impact', exact: true }).click();
  const review = page.getByRole('dialog', { name: 'Review permission impact' });
  await review.getByRole('button', { name: 'Apply changes' }).click();
  await expect(review.getByRole('status')).toContainText('Stale revision');
  expect(state.calls.find(call => call.path === '/api/control/apply').body.expected_revision).toBe(3);
  await page.keyboard.press('Escape');
  await expect(page.getByLabel('Permission rules').getByText('/fixtures/preserve-me', { exact: true })).toBeVisible();
});

test('unsupported ACL combinations surface backend rejection without applying policy', async ({ page }) => {
  const state = await fixture(page);
  await page.route('**/api/control/dry-run', route => route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'Directory write/create/delete cannot be independently enforced by ACLs.' }) }));
  await page.goto('/#/permissions');
  await page.getByRole('button', { name: 'Review impact', exact: true }).click();
  const review = page.getByRole('dialog', { name: 'Review permission impact' });
  await expect(review.getByRole('status')).toContainText('cannot be independently enforced');
  await expect(review.getByRole('button', { name: 'Apply changes' })).toHaveCount(0);
  expect(state.calls.filter(call => call.path === '/api/control/apply')).toHaveLength(0);
});

test('partial cut preserves failed items and upload sends raw bytes with CSRF', async ({ page }) => {
  const state = await fixture(page, { entries: [{ name: 'first.txt', path: '/first.txt', kind: 'file', size: 2 }, { name: 'collision.txt', path: '/collision.txt', kind: 'file', size: 2 }] });
  await page.route('**/api/fs/mutate', async route => {
    const body = route.request().postDataJSON();
    if (body.path === '/collision.txt') await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: 'Destination exists. Original file preserved.' }) });
    else await route.fallback();
  });
  await page.goto('/#/files');
  const nas = page.locator('#nas-browser');
  await nas.getByLabel('Select all visible files').check();
  await nas.getByRole('button', { name: 'Cut', exact: true }).click();
  await nas.getByRole('button', { name: 'Paste', exact: true }).click();
  const paste = page.getByRole('dialog', { name: 'Confirm move' });
  await paste.getByLabel('Destination folder').fill('/destination');
  await paste.getByRole('button', { name: 'Paste here' }).click();
  await expect(paste.getByRole('status')).toContainText('Original file preserved');
  await expect(nas.getByText(/1 to move/)).toBeVisible();
  await paste.getByRole('button', { name: 'Close', exact: true }).click();
  await nas.locator('input[name="upload"]').setInputFiles({ name: 'upload.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic-upload') });
  await expect(page.getByRole('dialog', { name: 'Upload to /' }).getByRole('status')).toContainText('uploaded');
  const upload = state.calls.find(call => call.path === '/api/fs/upload');
  expect(upload.method).toBe('PUT');
  expect(upload.headers['x-h07p-csrf']).toBe('fixture-csrf');
  expect(upload.url.searchParams.get('path')).toBe('/upload.txt');
});
