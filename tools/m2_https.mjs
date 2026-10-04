// Local M2 harness only; Azure continues to terminate HTTPS at App Service.
import { createServer } from 'node:https';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const next = require('next');
const profile = process.env.M2_LOCAL_PROFILE ?? 'initial';
if (!['initial', 'browser', 'mac', 'm3', 'm4', 'mac-flow'].includes(profile)) throw new Error('Unknown M2 local profile');
const local = ['m3', 'm4', 'mac-flow'].includes(profile) ? `${root}.${profile}-local/` : `${root}.m2-local/${profile === 'initial' ? '' : `${profile}/`}`;
const app = next({ dev: false, dir: `${root}frontend`, hostname: 'localhost', port: 8443 });
await app.prepare();
const handler = app.getRequestHandler();
const server = createServer({ key: readFileSync(`${local}tls/server.key`),
  cert: readFileSync(`${local}tls/server.crt`) }, (req, res) => handler(req, res));
server.listen(8443, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
