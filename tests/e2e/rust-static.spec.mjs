import { test, expect } from '@playwright/test';

test('migrated health and static assets are served by the actual Rust process', async ({ request }) => {
  expect(process.env.HUOU07_E2E_BACKEND).toBe('rust');
  const health = await request.get('/api/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ ok: true });
  expect(health.headers()['cache-control']).toBe('no-store');
  const shell = await request.get('/');
  expect(shell.status()).toBe(200);
  expect(shell.headers()['content-security-policy']).toContain("frame-ancestors 'none'");
  expect(await shell.text()).toContain('id="sidebar"');
  const script = await request.get('/navigation.js');
  expect(script.status()).toBe(200);
  expect(await script.text()).toContain('function closeNavigation');
  for (const asset of ['/product.js', '/product.css']) {
    expect((await request.get(asset)).status()).toBe(200);
  }
  // Real Rust responses, with no interception: anonymous callers cannot read
  // telemetry or owner data, and cannot mutate policy without a session.
  expect(await (await request.get('/api/owner/session')).json()).toEqual({ authenticated: false });
  for (const endpoint of ['/api/metrics', '/api/control/status', '/api/fs/list?area=nas&path=/']) {
    expect((await request.get(endpoint)).status()).toBe(401);
  }
  expect((await request.post('/api/control/apply', { data: {} })).status()).toBe(401);
});
