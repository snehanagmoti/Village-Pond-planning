import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, it } from 'vitest';


const nginxConfig = readFileSync(join(process.cwd(), 'nginx.conf'), 'utf8');


it('keeps browser security headers in locations that override cache headers', () => {
  for (const location of ['location /assets/', 'location / {']) {
    const start = nginxConfig.indexOf(location);
    const end = nginxConfig.indexOf('\n    }', start);
    const block = nginxConfig.slice(start, end);
    expect(start).toBeGreaterThan(-1);
    expect(block).toContain('add_header X-Content-Type-Options "nosniff" always;');
    expect(block).toContain('add_header X-Frame-Options "DENY" always;');
    expect(block).toContain('add_header Referrer-Policy "strict-origin-when-cross-origin" always;');
    expect(block).toContain('add_header Permissions-Policy');
    expect(block).toContain('add_header Content-Security-Policy');
  }
});
