// @vitest-environment jsdom

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import App from '../pages/src/App.jsx';
import { buildPersonalizationProfile, DEFAULT_FORM_STATE, INTEREST_CLUSTERS } from '../pages/src/profile.js';
import examples from '../shared/jev-preview.examples.json';

let container;
let root;
let user;

const json = (payload, status = 200) => new Response(JSON.stringify(payload), {
  status, headers: { 'content-type': 'application/json' }
});

function envelope(evaluations, overrides = {}) {
  return {
    contract_version: 'jev-preview-v1',
    summary: {
      correlation_id: 'fixture-run', dry_run: true, event_count: evaluations.length,
      rendered_count: evaluations.length ? 1 : 0, sent_count: 0, ...overrides
    },
    evaluations
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function mockApi(previewHandler, saveHandler) {
  const mock = vi.fn(async (path, options) => {
    if (path === '/api/me') return json({ user });
    if (path === '/api/digest/dry-run') return previewHandler(options);
    if (path === '/api/preferences') {
      const { preferences_blob } = JSON.parse(options.body);
      user = { ...user, preferences_blob };
      return saveHandler ? saveHandler(user) : json({ user });
    }
    if (path === '/api/logout') return json({ ok: true });
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

async function renderApp() {
  await act(async () => {
    root = createRoot(container);
    root.render(<App />);
  });
}

function button(text) {
  return [...container.querySelectorAll('button')].find((element) => element.textContent === text);
}

async function click(text) {
  const target = button(text);
  expect(target, `Button ${text} exists`).toBeDefined();
  await act(async () => target.click());
}

async function submit() {
  await act(async () => container.querySelector('form').requestSubmit());
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.history.replaceState({}, '', '/');
  container = document.createElement('div');
  document.body.append(container);
  const profile = buildPersonalizationProfile({ ...DEFAULT_FORM_STATE, interests: ['live_music', 'food_drink'] });
  user = { id: 'fixture-user', email: 'reader@example.com', preferences_blob: JSON.stringify(profile), is_subscribed: true };
});

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container.remove();
  vi.unstubAllGlobals();
});

describe('saved-profile Jev previews', () => {
  test('requests an authenticated body-free preview and displays the shared matched breakdown', async () => {
    const fetchMock = mockApi(() => json(envelope([examples.matched])));
    await renderApp();
    await click('Preview tomorrow safely');

    const [, options] = fetchMock.mock.calls.find(([path]) => path === '/api/digest/dry-run');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('include');
    expect(options.body).toBeUndefined();
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(container.querySelector('.evaluation-decision').textContent).toBe('Eligible for your digest');
    expect(container.querySelector('.evaluation-score').textContent).toContain('0 of 1. Limit: 0.6');
    expect(container.querySelector('.preview-selected-types').textContent).toBe('Live musicFood & drink');
    const details = container.querySelector('details');
    await act(async () => details.querySelector('summary').click());
    expect(details.open).toBe(true);
    const music = details.querySelector('li');
    expect(music.querySelector('h5').textContent).toBe('Live music');
    expect([...music.querySelectorAll('dd')].map((value) => value.textContent)).toEqual(['94%', '88%', '50%', '0']);
    expect(container.textContent).toContain('No email was sent');
    expect(document.activeElement).toBe(container.querySelector('#preview-title'));
  });

  test('allows a signed-in active user to preview while email delivery stays paused', async () => {
    user = { ...user, is_active: true, is_subscribed: false };
    const fetchMock = mockApi(() => json(envelope([examples.matched])));
    await renderApp();
    expect(container.textContent).toContain('DIGEST PAUSED');
    expect(button('Resume email digest')).toBeDefined();
    await click('Preview tomorrow safely');
    expect(container.querySelector('.evaluation-decision').textContent).toBe('Eligible for your digest');
    expect(user.is_subscribed).toBe(false);
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/me', '/api/digest/dry-run']);
    expect(container.textContent).toContain('No email was sent');
  });

  test.each([
    ['irrelevant', 'Irrelevant for your selected types', '0.85 of 1'],
    ['threshold_equality', 'Eligible for your digest', '0.6 of 1'],
    ['uncertain', 'Match not determined', 'No irrelevance score is available'],
    ['fallback', 'Match not determined', 'No irrelevance score is available']
  ])('renders the shared %s state without changing the backend decision', async (name, decision, score) => {
    mockApi(() => json(envelope([examples[name]], { failure_count: 0 })));
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.querySelector('.evaluation-decision').textContent).toBe(decision);
    expect(container.querySelector('.evaluation-score').textContent).toContain(score);
    if (name === 'irrelevant') expect(container.textContent).toContain('All evaluated events are irrelevant');
    if (['uncertain', 'fallback'].includes(name)) {
      expect(container.textContent).toContain('remains eligible for the usual ranking');
      expect(container.querySelector('.evaluation-score strong')).toBeNull();
    }
    if (name === 'uncertain') expect(container.querySelector('details').textContent).toContain('Not scored');
    if (name === 'fallback') expect(container.querySelector('details')).toBeNull();
  });

  test('distinguishes an empty collection from an all-irrelevant preview', async () => {
    mockApi(() => json(envelope([])));
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.textContent).toContain('No events found for tomorrow');
    expect(container.textContent).not.toContain('All evaluated events are irrelevant');
    expect(container.querySelector('.evaluation-card')).toBeNull();
    expect(button('Preview tomorrow safely').disabled).toBe(false);
  });

  test('shows a successful all-irrelevant preview even when no digest was rendered', async () => {
    mockApi(() => json(envelope([examples.irrelevant], { rendered_count: 0, failure_count: 0 })));
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.textContent).toContain('All evaluated events are irrelevant');
    expect(container.textContent).toContain('Rendered 0 private previews');
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(button('Retry preview')).toBeUndefined();
  });

  test.each([
    ['empty', []], ['nonempty', [examples.matched]]
  ])('offers retry for a failed preview with %s evaluations', async (_, evaluations) => {
    const response = vi.fn()
      .mockImplementationOnce(() => json(envelope(evaluations, { event_count: 1, failure_count: 1 })))
      .mockImplementationOnce(() => json(envelope([examples.matched], { failure_count: 0 })));
    mockApi(response);
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.querySelector('[role="alert"]').textContent).toContain('could not finish this preview');
    expect(container.querySelector('#preview-title')).toBeNull();
    expect(container.querySelector('.evaluation-card')).toBeNull();
    expect(container.textContent).not.toContain('No event-type evaluations are available');
    await click('Retry preview');
    expect(container.querySelector('.evaluation-card')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  test('keeps the legacy summary-only Worker response usable', async () => {
    const { summary } = envelope([examples.matched]);
    mockApi(() => json({ summary }));
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.textContent).toContain('1 event found for tomorrow');
    expect(container.textContent).toContain('Event-type explanations are not available yet');
    expect(container.textContent).toContain('fixture-run');
    expect(container.querySelector('.evaluation-card')).toBeNull();
  });

  test('announces loading and supports a retry after a failed request', async () => {
    const pending = deferred();
    const response = vi.fn().mockImplementationOnce(() => pending.promise).mockImplementationOnce(() => json(envelope([examples.matched])));
    mockApi(response);
    await renderApp();
    await click('Preview tomorrow safely');
    expect(button('Preparing…').disabled).toBe(true);
    expect(container.querySelector('[role="status"]').textContent).toContain('saved profile');
    await act(async () => pending.resolve(json({ error: 'private raw provider failure' }, 503)));
    expect(container.querySelector('[role="alert"]').textContent).toContain('temporarily unavailable');
    expect(container.textContent).not.toContain('private raw provider failure');
    expect(document.activeElement).toBe(container.querySelector('[role="alert"]'));
    await click('Retry preview');
    expect(container.querySelector('.evaluation-card')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  test('saves edits before the next preview and discards a late response from an older selection', async () => {
    const oldPreview = deferred();
    const save = deferred();
    const updated = structuredClone(examples.matched);
    updated.event.title = 'Current saved selection';
    updated.selected_event_types = ['live_music'];
    updated.components = [{ ...updated.components[0], weight: 1 }];
    const response = vi.fn().mockImplementationOnce(() => oldPreview.promise).mockImplementationOnce(() => json(envelope([updated], { correlation_id: 'newest-run' })));
    const fetchMock = mockApi(response, () => save.promise);
    await renderApp();
    await click('Preview tomorrow safely');
    const originalSignal = fetchMock.mock.calls.find(([path]) => path === '/api/digest/dry-run')[1].signal;
    await click('Edit my profile');
    expect(originalSignal.aborted).toBe(true);
    expect(container.querySelector('.digest-preview')).toBeNull();
    await submit(); // audience -> locations
    await submit(); // locations -> interests
    const foodIndex = INTEREST_CLUSTERS.findIndex((type) => type.name === 'food_drink');
    await act(async () => container.querySelectorAll('#interests-fieldset input')[foodIndex].click());
    await submit();
    await submit();
    await submit();
    await submit(); // save, deliberately held open
    expect(button('Saving…').disabled).toBe(true);
    expect(button('Preview tomorrow safely')).toBeUndefined();
    expect(response).toHaveBeenCalledTimes(1);
    const savedBody = JSON.parse(fetchMock.mock.calls.find(([path]) => path === '/api/preferences')[1].body);
    const savedProfile = JSON.parse(savedBody.preferences_blob);
    expect(Object.keys(savedProfile)).toHaveLength(6);
    expect(savedProfile.top_interest_clusters.map((type) => type.name)).toEqual(['live_music']);

    await act(async () => save.resolve(json({ user })));
    await click('Preview tomorrow safely');
    expect(container.querySelector('.preview-selected-types').textContent).toBe('Live music');
    expect(container.textContent).toContain('Current saved selection');
    await act(async () => oldPreview.resolve(json(envelope([examples.irrelevant], { correlation_id: 'stale-run' }))));
    expect(container.textContent).not.toContain('Architecture walking tour');
    expect(container.textContent).not.toContain('stale-run');
    expect(container.textContent).toContain('newest-run');
    expect(response).toHaveBeenCalledTimes(2);
  });

  test('signing out clears a pending preview even if its fetch ignores cancellation', async () => {
    const pending = deferred();
    mockApi(() => pending.promise);
    await renderApp();
    await click('Preview tomorrow safely');
    await click('Sign out');
    await act(async () => pending.resolve(json(envelope([examples.matched]))));
    expect(container.querySelector('#email').value).toBe('');
    expect(container.querySelector('.digest-preview')).toBeNull();
    expect(container.textContent).not.toContain(examples.matched.event.title);
  });

  test('an expired session returns to sign-in and never exposes an old preview', async () => {
    const response = vi.fn().mockImplementationOnce(() => json(envelope([examples.matched])))
      .mockImplementationOnce(() => json({ error: 'No session' }, 401));
    mockApi(response);
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.querySelector('.evaluation-card')).not.toBeNull();
    await click('Preview tomorrow safely');
    expect(container.textContent).toContain('Your session has expired');
    expect(button('Already registered? Resume setup')).toBeDefined();
    expect(container.querySelector('.digest-preview')).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('#email'));
  });

  test('does not offer an authenticated preview before a new registration verifies its email', async () => {
    const fetchMock = vi.fn(async (path) => {
      if (path === '/api/me') return json({ error: 'No session' }, 401);
      if (path === '/api/register') return json({ user });
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    await renderApp();
    await act(async () => {
      const email = container.querySelector('#email');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(email, user.email);
      email.dispatchEvent(new Event('input', { bubbles: true }));
    });
    for (let step = 0; step < 7; step += 1) await submit();
    expect(container.textContent).toContain('One quick step remains');
    expect(button('Preview tomorrow safely')).toBeUndefined();
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/me', '/api/register']);
  });

  test('requires review of unsupported saved selections instead of silently previewing defaults', async () => {
    const profile = JSON.parse(user.preferences_blob);
    profile.top_interest_clusters.push({ name: 'unknown_saved_type', includes: [] });
    user.preferences_blob = JSON.stringify(profile);
    const fetchMock = mockApi(() => json(envelope([examples.matched])));
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.querySelector('[role="alert"]').textContent).toContain('Edit and save your profile');
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/me']);
    expect(button('Retry preview')).toBeUndefined();
  });

  test('renders event titles as text and only links to validated web URLs', async () => {
    const evaluation = structuredClone(examples.matched);
    evaluation.event.title = '<img src=x onerror=alert(1)>';
    mockApi(() => json(envelope([evaluation])));
    await renderApp();
    await click('Preview tomorrow safely');
    const card = container.querySelector('.evaluation-card');
    expect(card.querySelector('img')).toBeNull();
    expect(card.querySelector('a').textContent).toContain(evaluation.event.title);
    expect(card.querySelector('a').getAttribute('href')).toBe(evaluation.event.url);
    expect(card.querySelector('a').getAttribute('rel')).toBe('noopener noreferrer');
  });

  test.each([
    ['unsafe URL', (evaluation) => { evaluation.event.url = 'javascript:alert(1)'; }],
    ['mismatched saved types', (evaluation) => { evaluation.selected_event_types = ['film']; }],
    ['malformed score', (evaluation) => { evaluation.irrelevance_score = '0'; }]
  ])('rejects a response with %s and offers retry', async (_, mutate) => {
    const evaluation = structuredClone(examples.matched);
    mutate(evaluation);
    mockApi(() => json(envelope([evaluation])));
    await renderApp();
    await click('Preview tomorrow safely');
    expect(container.querySelector('[role="alert"]').textContent).toContain('could not read this preview safely');
    expect(container.querySelector('.evaluation-card')).toBeNull();
    expect(button('Retry preview')).toBeDefined();
  });
});
