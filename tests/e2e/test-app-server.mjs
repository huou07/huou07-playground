import http from 'node:http';

const port = Number(process.env.HUOU07_E2E_APP_PORT);
const server = http.createServer((request, response) => {
  if (request.url === '/favicon.svg') {
    response.writeHead(200, { 'content-type': 'image/svg+xml' });
    response.end('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" fill="#4a8"/></svg>');
    return;
  }
  if (request.url === '/health') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end('{"ok":true}');
    return;
  }
  if (request.url === '/setup-health') {
    response.writeHead(307, { location: '/setup/1' });
    response.end();
    return;
  }
  if (request.url === '/setup/1') {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><title>Owner setup</title><h1>Complete owner setup</h1>');
    return;
  }
  if (request.url === '/') {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><title>Acceptance app</title><h1>Acceptance app launched</h1>');
    return;
  }
  response.writeHead(404);
  response.end();
});

server.listen(port, '127.0.0.1');
