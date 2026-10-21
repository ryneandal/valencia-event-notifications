// @vitest-environment jsdom

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import App from '../pages/src/App.jsx';
import { INTEREST_CLUSTERS } from '../pages/src/profile.js';

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
  test('supports bounded multi-selection, required validation, and back navigation', async () => {
    await renderApp();
    await act(async () => {
      const email = container.querySelector('#email');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(email, 'reader@example.com');
      email.dispatchEvent(new Event('input', { bubbles: true }));
    });
    for (let i = 0; i < 3; i += 1) {
      await act(async () => container.querySelector('form').requestSubmit());
    }

    const fieldset = container.querySelector('#interests-fieldset');
    expect(fieldset.querySelector('legend').textContent).toBe('Choose event types');
    expect(fieldset.querySelectorAll('input[type="checkbox"]')).toHaveLength(12);
    expect(fieldset.querySelectorAll('input:not([type="checkbox"])')).toHaveLength(0);
    for (const input of fieldset.querySelectorAll('input:checked')) {
      await act(async () => input.click());
    }
    await act(async () => container.querySelector('form').requestSubmit());
    expect(document.activeElement).toBe(fieldset);
    expect(fieldset.getAttribute('aria-describedby')).toContain('interests-error');
    expect(container.querySelector('#interests-error').textContent).toBe('Choose at least one event type from the list.');

    const selectType = async (name) => {
      const index = INTEREST_CLUSTERS.findIndex((option) => option.name === name);
      await act(async () => fieldset.querySelectorAll('input')[index].click());
    };
    await selectType('live_music');
    await selectType('food_drink');
    expect(container.querySelector('#interests-hint').textContent).toContain('2 of 12');
    expect(container.querySelector('#interests-error')).toBeNull();
    await act(async () => container.querySelector('form').requestSubmit());
    await act(async () => container.querySelector('.back-button').click());
    const chosen = [...container.querySelectorAll('#interests-fieldset input:checked')]
      .map((input) => input.closest('label').querySelector('strong').textContent);
    expect(chosen).toEqual(['Live music', 'Food & drink']);
  });

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
