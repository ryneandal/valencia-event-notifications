// @vitest-environment jsdom

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import App from '../pages/src/App.jsx';

let container;
let root;

async function renderApp() {
  await act(async () => {
    root = createRoot(container);
    root.render(<App />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.history.replaceState({}, '', '/');
  container = document.createElement('div');
  document.body.append(container);
  vi.stubGlobal('fetch', vi.fn(async () =>
    new Response(JSON.stringify({ error: 'No session' }), {
      status: 401,
      headers: { 'content-type': 'application/json' }
    })
  ));
});

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  container.remove();
  root = null;
  vi.unstubAllGlobals();
});

describe('onboarding accessibility behavior', () => {
  test('associates an invalid email message and focuses the field', async () => {
    await renderApp();

    await act(async () => container.querySelector('form').requestSubmit());

    const email = container.querySelector('#email');
    expect(email.getAttribute('aria-invalid')).toBe('true');
    expect(email.getAttribute('aria-describedby')).toContain('email-error');
    expect(container.querySelector('#email-error').textContent).toBe('Enter a valid email address.');
    expect(document.activeElement).toBe(email);
  });

  test('supports form submission and focuses the next step heading', async () => {
    await renderApp();
    const email = container.querySelector('#email');

    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      valueSetter.call(email, 'family@example.com');
      email.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => container.querySelector('form').requestSubmit());

    const heading = container.querySelector('#step-title');
    expect(heading.textContent).toBe('Who are we planning for?');
    expect(document.activeElement).toBe(heading);
    expect(container.querySelector('[role="progressbar"]').getAttribute('aria-valuenow')).toBe('2');
  });
});
