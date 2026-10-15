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
  // No intercept can turn an unimplemented API into Rust runtime parity.
  expect((await request.get('/api/metrics')).status()).toBe(404);
});
