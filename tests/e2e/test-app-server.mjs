import http from 'node:http';

const port = Number(process.env.HUOU07_E2E_APP_PORT);
const server = http.createServer((request, response) => {
  if (request.url === '/health') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end('{"ok":true}');
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
