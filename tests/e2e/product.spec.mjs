import { test, expect } from '@playwright/test';

const automaticSignIn = new WeakSet();
async function signInOwner(page) {
  const login = page.getByRole('dialog', { name: 'Owner sign in' });
  await expect(login).toBeVisible();
  await login.getByLabel('Username').fill('fixture-owner');
  await login.getByLabel('Password').fill('synthetic-password');
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(login).toHaveCount(0);
}
async function gotoOwner(page, path) {
  await page.goto(path);
  if (!automaticSignIn.has(page)) return;
  await page.evaluate(() => window.h07pSessionReady);
  if (!(await page.locator('#owner-account').textContent()).includes('Sign out')) await signInOwner(page);
}

// Browser interaction contracts use synthetic responses; they do not prove OS isolation.
async function fixture(page, { authenticated = true, entries = [], apps = [], failList = false } = {}) {
  const calls = [], files = [...entries], tickets = new Map();
  if (authenticated) automaticSignIn.add(page);
  let signedIn = authenticated, listFailure = failList;
  let policy = { revision: 3, enforced_revision: 3, preset: 'none', workspace: '/fixtures', workers: [{ name: 'worker-a', state: 'running', preset: 'none' }], rules: [], approvals: [], audit: [], capabilities: { mechanism: 'acl', independent_directory_rights: false } };
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    let body; try { body = request.postDataJSON(); } catch {}
    calls.push({ path, method: request.method(), body, headers: request.headers(), url });
    let response = {}, status = 200;
    const proof = request.headers()['x-h07p-csrf'] === 'fixture-csrf';
    const ticket = tickets.get(url.searchParams.get('ticket'));
    const ticketAllowed = ticket && path === '/api/fs/' + ticket.kind && url.searchParams.get('area') === ticket.area && url.searchParams.get('path') === ticket.path;
    if (!path.startsWith('/api/owner/') && path !== '/api/health' && (!signedIn || (!proof && !ticketAllowed))) return route.fulfill({ status: 401, json: { error: 'Owner proof required' } });
    if (path === '/api/owner/session') response = { authenticated: signedIn && proof, username: signedIn && proof ? 'fixture-owner' : undefined };
    else if (path === '/api/owner/login') { signedIn = true; response = { authenticated: true, username: 'fixture-owner', csrf: 'fixture-csrf' }; }
    else if (path === '/api/owner/logout') { signedIn = false; response = { ok: true }; }
    else if (path === '/api/control/status') response = policy;
    else if (path === '/api/control/dry-run') response = { ok: true, impact: { restart_workers: ['worker-a'], grants: [], revocations: [ '/fixtures/private' ] } };
    else if (path === '/api/control/apply') {
      if (body.expected_revision !== policy.revision) { status = 409; response = { error: 'Stale revision. Refresh and retry.' }; }
      else { policy = { ...policy, ...body, revision: 4, enforced_revision: 4 }; response = { ok: true, revision: 4, enforced_revision: 4 }; }
    } else if (path === '/api/control/scan') response = { findings: [{ path: '/fixtures/.env', reason: 'credential filename', confidence: 'high' }, { path: '/fixtures/readme.md', reason: 'No known sensitive marker', confidence: 'medium' }], skipped: [{ path: '/fixtures/unreadable', reason: 'Permission denied' }], partial: true };
    else if (path === '/api/fs/ticket') {
      const ticket = 'fixture-ticket-' + tickets.size; tickets.set(ticket, body);
      response = { url: '/api/fs/' + body.kind + '?' + new URLSearchParams({ area: body.area, path: body.path, ticket }) };
    } else if (path === '/api/fs/list') {
      if (listFailure) { listFailure = false; status = 403; response = { error: 'Permission denied for fixture path' }; }
      else response = { path: url.searchParams.get('path'), parent: '/', private: url.searchParams.get('area') === 'nas', entries: files, total: files.length, capacity: { total: 10737418240, used: 2147483648, free: 8589934592, available: 7516192768 } };
    } else if (path === '/api/fs/mutate') {
      if (body.action === 'mkdir') files.push({ name: body.path.split('/').at(-1), path: body.path, kind: 'directory' });
      if (body.action === 'rename') { const entry = files.find(item => item.path === body.path); if (entry) { entry.path = body.destination; entry.name = body.destination.split('/').at(-1); } }
      if (body.action === 'delete') { const index = files.findIndex(item => item.path === body.path); if (index >= 0) files.splice(index, 1); }
      response = { ok: true };
    } else if (path === '/api/fs/download') {
      return route.fulfill({ contentType: 'application/octet-stream', headers: { 'Content-Disposition': 'attachment; filename=fixture.bin' }, body: 'fixture-download' });
    } else if (path === '/api/fs/preview') {
      if (/\.png$/.test(url.searchParams.get('path'))) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64') });
      if (/\.webm$/.test(url.searchParams.get('path'))) return route.fulfill({ contentType: 'video/webm', body: '' });
      return route.fulfill({ contentType: 'text/plain', body: '<img src=x onerror="window.fixtureExecuted=true"> fixture text' });
    } else if (path === '/api/fs/upload') response = { ok: true };
    else if (path === '/api/metrics') response = { supported: true, sampled_at: 1700000000, cpu: { usage_percent: 12, logical_cores: 4 }, memory: { total: 8589934592, used: 2147483648, available: 6442450944, percent: 25 }, storage: { total: 107374182400, used: 21474836480, free: 85899345920, percent: 20 }, storage_devices: [], system: { hostname: 'fixture', os: 'Debian fixture' } };
    else if (path === '/api/apps') response = { available: true, total: apps.length, apps };
    else if (path === '/api/apps/icon') return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64') });
    else if (path === '/api/apps/launch' && url.searchParams.get('format') === 'json') response = { url: url.origin + '/fixture-harness/?token=synthetic-onetime' };
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
  await gotoOwner(page, '/#/files');
  const login = page.getByRole('dialog', { name: 'Owner sign in' });
  await expect(login).toBeVisible();
  expect(calls.filter(call => !call.path.startsWith('/api/owner/'))).toHaveLength(0);
  await login.getByLabel('Username').fill('fixture-owner');
  await login.getByLabel('Password').fill('synthetic-password');
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('button', { name: 'private.txt', exact: true })).toBeVisible();
  expect(calls.some(call => call.path === '/api/metrics')).toBe(true);
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toMatch(/fixture-csrf|synthetic-password/);
  await page.getByRole('button', { name: 'fixture-owner · Sign out' }).click();
  await expect(page.getByRole('button', { name: 'private.txt', exact: true })).toHaveCount(0);
  expect(calls.find(call => call.path === '/api/owner/logout').headers['x-h07p-csrf']).toBe('fixture-csrf');
});

test('permission drafts require dry-run and explicit apply; backend confirmation controls enforced status', async ({ page }) => {
  const { calls } = await fixture(page);
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await gotoOwner(page, '/#/permissions');
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
  await gotoOwner(page, '/#/permissions');
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
  await gotoOwner(page, '/#/files');
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
  await gotoOwner(page, '/#/storage');
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
  await gotoOwner(page, '/#/permissions');
  await expect(page.getByRole('button', { name: 'Review impact', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  const screenshot = testInfo.outputPath('permissions-light-360.png');
  await page.screenshot({ fullPage: true, path: screenshot, animations: 'disabled' });
  await testInfo.attach('permissions-light-360', { path: screenshot, contentType: 'image/png' });
  expect(errors).toEqual([]);
});

test('refreshing server status preserves a draft base revision and stale apply retains inputs', async ({ page }) => {
  const state = await fixture(page);
  await gotoOwner(page, '/#/permissions');
  await page.getByRole('button', { name: 'Block', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'New permission rule' });
  await editor.getByLabel('Absolute target path').fill('/fixtures/preserve-me');
  await editor.getByRole('button', { name: 'Save draft rule' }).click();
  state.setPolicy({ ...state.getPolicy(), revision: 7, enforced_revision: 7 });
  await gotoOwner(page, '/#/home');
  await gotoOwner(page, '/#/permissions');
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
  await gotoOwner(page, '/#/permissions');
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
  await gotoOwner(page, '/#/files');
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

test('legacy application editor sends owner CSRF and refreshes telemetry immediately after login', async ({ page }) => {
  const state = await fixture(page, { authenticated: false });
  await gotoOwner(page, '/#/home');
  const login = page.getByRole('dialog', { name: 'Owner sign in' });
  await login.getByLabel('Username').fill('fixture-owner');
  await login.getByLabel('Password').fill('synthetic-password');
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.locator('#connection-label')).toHaveText('Connected');
  await page.locator('#sidebar [data-route="settings"]').click();
  await page.locator('#app-form input[name="name"]').fill('CSRF fixture');
  await page.locator('#app-form input[name="url"]').fill('https://fixture.invalid/');
  await page.getByRole('button', { name: 'Add application', exact: true }).click();
  await expect(page.locator('#app-form-status')).toHaveText('Saved.');
  const save = state.calls.find(call => call.path === '/api/apps' && call.method === 'POST');
  expect(save.headers['x-h07p-csrf']).toBe('fixture-csrf');
  expect(save.body.app.name).toBe('CSRF fixture');
});

test('numeric expiry and decided approvals match the Rust helper contract', async ({ page }) => {
  const state = await fixture(page);
  const now = Math.floor(Date.now() / 1000);
  state.setPolicy({ ...state.getPolicy(), approvals: [
    { id: 'decided', worker: 'worker-a', operation: 'read', target: '/fixtures/decided', revision: 3, expires_at: now + 300, state: 'approved' },
    { id: 'pending', worker: 'worker-a', operation: 'read', target: '/fixtures/pending', revision: 3, expires_at: now + 300, state: 'pending' },
  ], audit: [{ at: now, event: 'Fixture audit entry' }] });
  await gotoOwner(page, '/#/permissions');
  await expect(page.getByRole('button', { name: 'Approve once' }).nth(0)).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Approve once' }).nth(1)).toBeEnabled();
  await expect(page.getByText(/Fixture audit entry/)).toBeVisible();
  await expect(page.getByText(/Revision undefined/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Block', exact: true }).click();
  const editor = page.getByRole('dialog', { name: 'New permission rule' });
  await editor.getByLabel('Absolute target path').fill('/fixtures/expiring');
  const future = new Date((now + 3600) * 1000);
  const local = new Date(future.getTime() - future.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  await editor.getByLabel('Expiry').fill(local);
  await editor.getByRole('button', { name: 'Save draft rule' }).click();
  await page.getByRole('button', { name: 'Review impact', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Review permission impact' }).getByRole('button', { name: 'Apply changes' })).toBeVisible();
  const rule = state.calls.find(call => call.path === '/api/control/dry-run').body.rules[0];
  expect(typeof rule.expires_at).toBe('number');
  expect(rule.expires_at).toBeGreaterThan(now);
  expect(rule.expires_at).toBeLessThanOrEqual(now + 3600);
});

test('content scanning requires explicit scoped opt-in and never displays source excerpts', async ({ page }) => {
  const state = await fixture(page);
  await gotoOwner(page, '/#/permissions');
  await page.getByRole('button', { name: 'Auto Detect', exact: true }).click();
  const scan = page.getByRole('dialog', { name: 'Auto Detect · review suggestions' });
  const content = scan.getByLabel('Include bounded content scan (Gitleaks)', { exact: true });
  await expect(content).not.toBeChecked();
  await scan.getByLabel('Scope (absolute path)', { exact: true }).fill('/fixtures/selected-scope');
  await content.check();
  await scan.getByRole('button', { name: 'Start scan' }).click();
  await expect(scan.getByRole('status')).toContainText('Nothing has changed.');
  expect(state.calls.find(call => call.path === '/api/control/scan').body).toMatchObject({ scope: '/fixtures/selected-scope', content: true });
  await expect(scan.locator('pre')).toHaveCount(0);
  await expect(scan.getByRole('button', { name: 'Review selected' })).toBeDisabled();
});

test('failed login retains username, clears password and permits safe retry', async ({ page }) => {
  await fixture(page, { authenticated: false });
  let attempts = 0;
  await page.route('**/api/owner/login', async route => {
    if (++attempts === 1) await route.fulfill({ status: 401, json: { error: 'Invalid owner credentials' } });
    else await route.fallback();
  });
  await gotoOwner(page, '/#/home');
  const login = page.getByRole('dialog', { name: 'Owner sign in' });
  await login.getByLabel('Username').fill('fixture-owner');
  await login.getByLabel('Password').fill('synthetic-wrong');
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(login.getByRole('status')).toHaveText('Invalid owner credentials');
  await expect(login.getByLabel('Username')).toHaveValue('fixture-owner');
  await expect(login.getByLabel('Password')).toHaveValue('');
  await login.getByLabel('Password').fill('synthetic-correct');
  await login.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(login).toHaveCount(0);
  await expect(page.locator('#connection-label')).toHaveText('Connected');
});

test('VPN HTTP API availability supports sign-in and new rule dialogs', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(Crypto.prototype, 'randomUUID', { value: undefined }));
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await fixture(page, { authenticated: false });
  await gotoOwner(page, '/#/permissions');
  await signInOwner(page);
  await page.getByRole('button', { name:'Block', exact:true }).click();
  const rule=page.getByRole('dialog', { name:'New permission rule' });
  await rule.getByLabel('Absolute target path').fill('/fixtures/closed-export.log');
  await rule.getByRole('button', { name:'Save draft rule' }).click();
  await expect(rule).toHaveCount(0);
  await expect(page.locator('[aria-label="Permission rules"]')).toContainText('/fixtures/closed-export.log');
  expect(errors).toEqual([]);
});

test('NAS and Storage search scopes filenames and opens a result folder', async ({ page }) => {
  await fixture(page);
  const requests=[];
  await page.route('**/api/fs/search',async route=>{
    requests.push(route.request().postDataJSON());
    expect(route.request().headers()['x-h07p-csrf']).toBe('fixture-csrf');
    await route.fulfill({json:{path:'/',entries:[{name:'Report.txt',path:'/nested/Report.txt',kind:'file',size:12}],total:1,visited:20,partial:true,private:true}});
  });
  for(const [routeName,area,label] of [['files','nas','Search NAS filenames'],['storage','storage','Search Storage filenames']]){
    await gotoOwner(page,'/#/'+routeName);
    const browser=page.locator(area==='nas'?'#nas-browser':'#host-browser');
    await browser.getByRole('searchbox',{name:label}).fill('Report');
    await browser.getByRole('button',{name:'Search',exact:true}).click();
    await expect(browser.getByRole('status').first()).toContainText('Partial results');
    await expect(browser.getByText('/nested/Report.txt',{exact:true})).toBeVisible();
    expect(requests.at(-1)).toMatchObject({area,path:'/',query:'Report',recursive:true});
    await browser.getByRole('button',{name:'Open folder',exact:true}).click();
    await expect(browser.getByRole('textbox',{name:area==='nas'?'NAS path':'Host path',exact:true})).toHaveValue('/nested');
  }
});

test('worker scope changes only the selected settings and all-worker change clears overrides',async({page})=>{
  const state=await fixture(page);
  state.setPolicy({...state.getPolicy(),workers:[{name:'dsh-worker',preset:'none'},{name:'codex-worker',preset:'none'}]});
  await gotoOwner(page,'/#/permissions');
  await page.getByLabel('Configure worker',{exact:true}).selectOption('dsh-worker');
  await page.getByLabel('Security Level',{exact:true}).selectOption('strict');
  const review=page.getByRole('dialog',{name:'Review Security Level change'});
  await review.getByRole('button',{name:'Keep custom rules'}).click();
  await page.getByRole('button',{name:'Review impact',exact:true}).click();
  const impact=page.getByRole('dialog',{name:'Review permission impact'});
  await expect(impact).toContainText('Individual worker settings');
  let call=state.calls.filter(c=>c.path==='/api/control/dry-run').at(-1);
  expect(call.body.worker_settings).toEqual({'dsh-worker':{preset:'strict'}});
  expect(call.body.preset).toBe('none');
  await page.keyboard.press('Escape');
  await page.getByLabel('Configure worker',{exact:true}).selectOption('*');
  await page.getByLabel('Security Level',{exact:true}).selectOption('minimal');
  await page.getByRole('dialog',{name:'Review Security Level change'}).getByRole('button',{name:'Keep custom rules'}).click();
  await page.getByRole('button',{name:'Review impact',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Review permission impact'})).toContainText('Individual worker settings');
  call=state.calls.filter(c=>c.path==='/api/control/dry-run').at(-1);
  expect(call.body.preset).toBe('minimal');expect(call.body.worker_settings['dsh-worker'].preset).toBeUndefined();
});

test('expired session clears private files and telemetry before prompting for sign-in', async ({ page }) => {
  await fixture(page, { entries: [{ name: 'private-fixture.txt', path: '/private-fixture.txt', kind: 'file', size: 4 }] });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await gotoOwner(page, '/#/files');
  await expect(page.getByRole('button', { name: 'private-fixture.txt', exact: true })).toBeVisible();
  await expect(page.locator('#cpu-value')).toHaveText('12%');
  await page.route('**/api/fs/list?**', route => route.fulfill({ status: 401, json: { error: 'Owner sign in required' } }));
  await page.locator('#nas-browser').getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Owner sign in' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'private-fixture.txt', exact: true })).toHaveCount(0);
  await expect(page.locator('#cpu-value')).toHaveText('N/A');
  await expect(page.locator('#connection-label')).toHaveText('Owner sign in required');
  expect(errors).toEqual([]);
});


test('cookie alone reveals no owner proof and reload requires signing in again', async ({ page }) => {
  const { calls } = await fixture(page);
  await page.goto('/#/files');
  await expect(page.getByRole('dialog', { name: 'Owner sign in' })).toBeVisible();
  expect(calls.filter(call => !call.path.startsWith('/api/owner/'))).toHaveLength(0);
  await signInOwner(page);
  const confirmation = calls.filter(call => call.path === '/api/owner/session').at(-1);
  expect(confirmation.headers['x-h07p-csrf']).toBe('fixture-csrf');
  const beforeReload = calls.length;
  await page.reload();
  await expect(page.getByRole('dialog', { name: 'Owner sign in' })).toBeVisible();
  const afterReload = calls.slice(beforeReload);
  expect(afterReload.filter(call => !call.path.startsWith('/api/owner/'))).toHaveLength(0);
  expect(afterReload.find(call => call.path === '/api/owner/session').headers['x-h07p-csrf']).toBeUndefined();
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain('fixture-csrf');
});

test('login proof accompanies every private API GET including text preview and session confirmation', async ({ page }) => {
  const { calls } = await fixture(page, { entries: [{ name: 'proof.txt', path: '/proof.txt', kind: 'file', size: 8 }] });
  await gotoOwner(page, '/#/files');
  await page.getByRole('button', { name: 'proof.txt', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'proof.txt' }).locator('pre')).toBeVisible();
  const privateReads = calls.filter(call => call.method === 'GET' && !['/api/owner/session', '/api/health'].includes(call.path));
  expect(privateReads.some(call => call.path === '/api/metrics')).toBe(true);
  expect(privateReads.some(call => call.path === '/api/fs/preview')).toBe(true);
  for (const call of privateReads) expect(call.headers['x-h07p-csrf'], call.path).toBe('fixture-csrf');
  expect(calls.filter(call => call.path === '/api/owner/session').at(-1).headers['x-h07p-csrf']).toBe('fixture-csrf');
});

test('image video and download browser requests use path-scoped tickets without owner proof in URLs', async ({ page }) => {
  const { calls } = await fixture(page, { entries: [{ name: 'photo.png', path: '/photo.png', kind: 'file', size: 90 }, { name: 'clip.webm', path: '/clip.webm', kind: 'file', size: 100 }] });
  await gotoOwner(page, '/#/files');
  await page.getByRole('button', { name: 'photo.png', exact: true }).click();
  const image = page.getByRole('dialog', { name: 'photo.png' }).getByRole('img');
  await expect(image).toHaveAttribute('src', /ticket=fixture-ticket-/);
  expect(new URL(await image.getAttribute('src')).searchParams.get('path')).toBe('/photo.png');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'clip.webm', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'clip.webm' }).locator('video')).toHaveAttribute('src', /ticket=fixture-ticket-/);
  await page.keyboard.press('Escape');
  await page.getByLabel('Select photo.png', { exact: true }).check();
  const downloaded = page.waitForEvent('download');
  await page.locator('#nas-browser').getByRole('button', { name: 'Download', exact: true }).click();
  await downloaded;
  const tickets = calls.filter(call => call.path === '/api/fs/ticket');
  expect(tickets.some(call => call.body.kind === 'preview' && call.body.path === '/photo.png')).toBe(true);
  expect(tickets.some(call => call.body.kind === 'preview' && call.body.path === '/clip.webm')).toBe(true);
  expect(tickets.some(call => call.body.kind === 'download')).toBe(true);
  for (const call of tickets) expect(call.headers['x-h07p-csrf']).toBe('fixture-csrf');
  for (const call of calls.filter(call => ['/api/fs/preview', '/api/fs/download'].includes(call.path))) {
    expect(call.url.searchParams.get('ticket')).toMatch(/^fixture-ticket-/);
    expect(call.url.href).not.toContain('fixture-csrf');
    expect(call.headers['x-h07p-csrf']).toBeUndefined();
  }
});

test('ticket rejection keeps browser media requests from starting and shows a recoverable error', async ({ page }) => {
  const { calls } = await fixture(page, { entries: [{ name: 'blocked.png', path: '/blocked.png', kind: 'file', size: 90 }] });
  await page.route('**/api/fs/ticket', route => route.fulfill({ status: 403, json: { error: 'File access denied. Retry after signing in.' } }));
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await gotoOwner(page, '/#/files');
  await page.getByRole('button', { name: 'blocked.png', exact: true }).click();
  const preview = page.getByRole('dialog', { name: 'blocked.png' });
  await expect(preview.getByRole('status')).toContainText('File access denied');
  await expect(preview.getByRole('img')).toHaveCount(0);
  await expect(preview.getByRole('link', { name: 'Download file' })).toHaveCount(0);
  expect(calls.filter(call => ['/api/fs/preview', '/api/fs/download'].includes(call.path))).toHaveLength(0);
  expect(errors).toEqual([]);
});

test('app icons use authenticated blobs and harness launch fetches its private URL before navigating', async ({ page }) => {
  await page.context().route('**/fixture-harness/**', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Synthetic harness fixture</title><p>Fixture destination</p>' }));
  await page.addInitScript(() => {
    window.fixtureRevoked = [];
    const revoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = value => { window.fixtureRevoked.push(value); revoke(value); };
  });
  const { calls } = await fixture(page, { apps: [
    { name: 'DeepSeek Harness', url: 'http://127.0.0.1:3080/', category: 'Tools', status: 'available' },
    { name: 'Ordinary', url: 'https://example.invalid/ordinary', category: 'Tools', status: 'unmonitored' },
  ] });
  await gotoOwner(page, '/#/apps');
  await expect(page.locator('.app-icon').first()).toHaveAttribute('src', /^blob:/);
  const iconCalls = calls.filter(call => call.path === '/api/apps/icon');
  expect(iconCalls.length).toBeGreaterThan(0);
  for (const call of iconCalls) expect(call.headers['x-h07p-csrf']).toBe('fixture-csrf');
  const ordinary = page.getByRole('link', { name: 'Open Ordinary', exact: true });
  await expect(ordinary).toHaveAttribute('href', 'https://example.invalid/ordinary');
  const opened = page.waitForEvent('popup');
  await page.getByRole('link', { name: 'Open DeepSeek Harness', exact: true }).click();
  const popup = await opened;
  await expect(popup).toHaveURL(/fixture-harness\/\?token=synthetic-onetime/);
  const launch = calls.find(call => call.path === '/api/apps/launch');
  expect(launch.url.searchParams.get('format')).toBe('json');
  expect(launch.headers['x-h07p-csrf']).toBe('fixture-csrf');
  expect(launch.url.href).not.toContain('fixture-csrf');
  await popup.close();
  await page.getByRole('button', { name: 'fixture-owner · Sign out' }).click();
  await expect(page.locator('.app-icon')).toHaveCount(0);
  expect((await page.evaluate(() => window.fixtureRevoked)).length).toBeGreaterThan(0);
});
