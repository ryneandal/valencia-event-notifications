import { describe, expect, test, vi } from 'vitest';

import { onRequest, proxyApiRequest } from '../../functions/api/[[path]].js';

describe('Pages API proxy', () => {
  test('forwards the path, query, method, headers, and body to the Worker', async () => {
    const fetchImpl = vi.fn(async () => new Response('{"ok":true}', { status: 200 }));
    const request = new Request(
      'https://valencia-event-notifications.pages.dev/api/preferences?source=dashboard',
      {
        method: 'PATCH',
        headers: {
          'content-type': 'application/json',
          cookie: 'ven_session=test-session'
        },
        body: '{"audience":"family"}'
      }
    );

    await proxyApiRequest(request, 'https://worker.example', fetchImpl);

    const proxiedRequest = fetchImpl.mock.calls[0][0];
    expect(proxiedRequest.url).toBe(
      'https://worker.example/api/preferences?source=dashboard'
    );
    expect(proxiedRequest.method).toBe('PATCH');
    expect(proxiedRequest.headers.get('cookie')).toBe('ven_session=test-session');
    expect(await proxiedRequest.text()).toBe('{"audience":"family"}');
  });

  test('uses the configured Worker URL', async () => {
    const fetchImpl = vi.fn(async () => new Response('{"ok":true}', { status: 200 }));
    vi.stubGlobal('fetch', fetchImpl);

    await onRequest({
      request: new Request('https://dashboard.example/api/health'),
      env: { API_BASE_URL: 'https://configured-worker.example' }
    });

    expect(fetchImpl.mock.calls[0][0].url).toBe(
      'https://configured-worker.example/api/health'
    );
    vi.unstubAllGlobals();
  });
});
