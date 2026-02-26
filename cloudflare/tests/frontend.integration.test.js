import fs from 'node:fs';
import path from 'node:path';

import { JSDOM } from 'jsdom';
import { describe, expect, test } from 'vitest';

import { createDashboardApp } from '../pages/public/app.js';

function loadDom() {
  const htmlPath = path.join(process.cwd(), 'pages', 'public', 'index.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html);
  return dom;
}

async function waitForAsyncUiTick() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('frontend integration', () => {
  test('register flow updates status and profile output', async () => {
    const dom = loadDom();
    const { document } = dom.window;

    const fetchCalls = [];
    const fetchImpl = async (url, options) => {
      fetchCalls.push({ url, options });
      return {
        ok: true,
        async json() {
          return {
            user: {
              id: 1,
              email: 'dashboard@example.com',
              preferences_blob: '{"audience":"family"}',
              is_active: true
            }
          };
        }
      };
    };

    createDashboardApp({ document, fetchImpl });

    document.getElementById('register-email').value = 'dashboard@example.com';
    document.getElementById('register-preferences').value = '{"audience":"family"}';

    document.getElementById('register-form').dispatchEvent(
      new dom.window.Event('submit', { bubbles: true, cancelable: true })
    );

    await waitForAsyncUiTick();

    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0].url).toBe('/api/register');
    expect(fetchCalls[0].options.credentials).toBe('include');
    expect(document.getElementById('status').textContent).toBe('Registered and signed in.');
    expect(document.getElementById('profile-output').textContent).toContain(
      'dashboard@example.com'
    );
  });

  test('refresh profile shows unauthorized message when session is missing', async () => {
    const dom = loadDom();
    const { document } = dom.window;

    const fetchImpl = async () => ({
      ok: false,
      status: 401,
      async json() {
        return { error: 'Unauthorized' };
      }
    });

    createDashboardApp({ document, fetchImpl });

    document
      .getElementById('me-button')
      .dispatchEvent(new dom.window.Event('click', { bubbles: true, cancelable: true }));

    await waitForAsyncUiTick();

    expect(document.getElementById('status').textContent).toBe('Unauthorized');
  });
});
