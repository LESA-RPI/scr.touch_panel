import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('commands are sent once and unknown receipts eventually release', async (t) => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 1000 });
  const source = await readFile(new URL('../browser/js/api.js', import.meta.url), 'utf8');
  const api = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  let state = { available: true, session: 'one', revision: 'one:1', lights: { state: 'ready' } };
  const commands = [];
  let offline = false;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url === '/api/command') {
      commands.push(JSON.parse(options.body));
      throw new Error('Reply lost');
    }
    if (offline) throw new Error('Offline');
    return { json: async () => state };
  });
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  await api.poll();

  await api.send('off');
  await flush();
  assert.equal(api.store.pending.status, 'unknown');
  assert.equal(await api.send('off'), false);
  await api.poll();
  assert.equal(commands.length, 1);
  t.mock.timers.tick(19999);
  await api.poll();
  assert.ok(api.store.pending);
  offline = true;
  t.mock.timers.tick(2);
  await api.poll();
  assert.equal(api.store.pending, null);
  assert.equal(commands.length, 1);

  offline = false;
  await api.poll();
  await api.send('off');
  await flush();
  state = { ...state, receipts: [{ id: commands[1].id, ok: true, code: 202 }] };
  await api.poll();
  assert.equal(api.store.pending, null);
  assert.equal(api.busy(), false);

  await api.send('off');
  await flush();
  state = { ...state, session: 'two' };
  await api.poll();
  assert.equal(api.store.pending, null);
  assert.equal(commands.length, 3);
  assert.equal(new Set(commands.map((command) => command.id)).size, 3);
});
