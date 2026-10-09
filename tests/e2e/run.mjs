import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const temp = mkdtempSync(join(tmpdir(), 'huou07-playground-e2e-'));
const children = [];

async function freePort() {
  const server = createServer();
  await new Promise((resolveListen, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const { port } = server.address();
  await new Promise(resolveClose => server.close(resolveClose));
  return port;
}

function start(command, args, env) {
  const child = spawn(command, args, { cwd: root, env, stdio: 'ignore' });
  children.push(child);
  return child;
}

async function waitFor(url, child, name) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`${name} exited before becoming ready.`);
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise(resolveDelay => setTimeout(resolveDelay, 100));
  }
  throw new Error(`${name} did not become ready at ${url}.`);
}

async function stopChildren() {
  for (const child of children) if (child.exitCode === null) child.kill('SIGTERM');
  await Promise.all(children.map(child => new Promise(resolveExit => {
    if (child.exitCode !== null) return resolveExit();
    const timeout = setTimeout(() => {
      if (child.exitCode === null) child.kill('SIGKILL');
      resolveExit();
    }, 3000);
    child.once('exit', () => { clearTimeout(timeout); resolveExit(); });
  })));
}

try {
  const dashboardPort = await freePort();
  const appPort = await freePort();
  const registry = join(temp, 'apps.json');
  writeFileSync(registry, '{"apps":[]}\n', { mode: 0o600 });
  const baseUrl = `http://127.0.0.1:${dashboardPort}`;
  const appUrl = `http://127.0.0.1:${appPort}/`;
  const appServer = start(process.execPath, [join(root, 'tests/e2e/test-app-server.mjs')], {
    ...process.env,
    HUOU07_E2E_APP_PORT: String(appPort),
  });
  const dashboard = start(process.env.PYTHON || 'python3', [join(root, 'web/app.py')], {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(dashboardPort),
    APPS_FILE: registry,
  });
  await Promise.all([
    waitFor(appUrl, appServer, 'Acceptance application'),
    waitFor(`${baseUrl}/api/health`, dashboard, 'Dashboard'),
  ]);

  const result = spawnSync(process.execPath, [
    join(root, 'node_modules/@playwright/test/cli.js'), 'test', '--config=playwright.config.mjs',
  ], {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      HUOU07_E2E_BASE_URL: baseUrl,
      HUOU07_E2E_APP_URL: appUrl,
      HUOU07_E2E_APP_HEALTH_URL: `${appUrl}health`,
    },
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  await stopChildren();
  rmSync(temp, { recursive: true, force: true });
}
