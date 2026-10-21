// @vitest-environment jsdom

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import App from '../pages/src/App.jsx';
import DigestPreview from '../pages/src/DigestPreview.jsx';
import { parseDigestPreview } from '../pages/src/preview.js';
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
    if (path === '/api/billing') return json({ membership: { available: false, active: false, can_manage: false, status: 'none' } });
    if (path === '/api/planning') return json({
      version: 'brisa-planning-v1', today: '2026-10-21',
      available_dates: ['2026-10-22', '2026-10-23', '2026-10-24', '2026-10-25', '2026-10-26', '2026-10-27', '2026-10-28'],
      delivery_enabled: false, delivery_days: [0, 1, 2, 3, 4, 5, 6],
      subscribed: user.is_subscribed, saved_events: [], pilot: { consented: false, expires_at: null },
      membership: { interested: false, price_eur: 3, phase: 'interest_test' }, coverage_history: []
    });
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
  return [...container.querySelectorAll('button')].find((element) => (element.getAttribute('aria-label') || element.textContent) === text);
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
  const profile = buildPersonalizationProfile({ ...DEFAULT_FORM_STATE, audience: 'family_with_school_age_kids', locations: ['Valencia city'], interests: ['live_music', 'food_drink'] });
  user = { id: 'fixture-user', email: 'reader@example.com', preferences_blob: JSON.stringify(profile), is_subscribed: true };
});

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function planningPayload({ state = 'complete', empty = false, filtered = false } = {}) {
  const matched = structuredClone(examples.matched);
  const otherMatch = structuredClone(examples.matched);
  otherMatch.event = { event_key: 'fixture-second', title: 'Another concert', url: 'https://example.org/second' };
  const irrelevant = structuredClone(examples.irrelevant);
  const evaluations = empty ? [] : filtered ? [irrelevant] : [matched, otherMatch, irrelevant];
  const publicEvent = (evaluation, id, position) => ({
    id, ...evaluation.event, start_at: '2026-10-22T19:00:00+02:00', end_at: null,
    time_precision: 'datetime', location: 'Plaça del Mercat, València',
    description: 'A public description.', source: 'ajuntament_agenda', position,
    reason: 'Suggested from your saved choices.', used_fallback: false, type_decision: evaluation.decision
  });
  const sources = [{ name: 'ajuntament_agenda', status: state === 'unavailable' ? 'error' : 'ok', fetched_count: 8, event_count: evaluations.length, checked_at: '2026-10-21T20:00:00Z' }];
  if (state === 'partial') sources.push({ name: 'other_source', status: 'error', fetched_count: 0, event_count: 0, checked_at: '2026-10-21T20:00:00Z' });
  return {
    ...envelope(evaluations),
    plans: {
      version: 'brisa-plans-v1', date: '2026-10-22', checked_at: '2026-10-21T20:00:00Z',
      delivery_enabled: false, coverage: { state, collected_count: evaluations.length, sources },
      recommendations: empty || filtered ? [] : [publicEvent(otherMatch, 8, 1), publicEvent(matched, 7, 2)],
      excluded_count: empty ? 0 : 1
    }
  };
}

async function renderPreview(payload, props = {}) {
  const result = parseDigestPreview(payload, ['live_music', 'food_drink']);
  await act(async () => {
    root = createRoot(container);
    root.render(<DigestPreview state={{ status: 'ready', result }} {...props} />);
  });
}

function planButton(label, within = container) {
  return [...within.querySelectorAll('button')].find((element) => element.textContent.startsWith(label));
}

describe('recommendation-first planning preview', () => {
  test('uses actual ranking order and keeps other evaluations and numeric details collapsed', async () => {
    const payload = planningPayload();
    await renderPreview(payload);
    const titles = [...container.querySelectorAll('.plan-card h4')].map((heading) => heading.textContent);
    expect(titles).toEqual(['Another concert', 'Jazz in the garden']);
    expect(container.querySelector('.plan-list').textContent).not.toContain(examples.irrelevant.event.title);
    expect(container.querySelector('.preview-other-events').textContent).toContain(examples.irrelevant.event.title);
    expect(container.querySelector('.preview-other-events').open).toBe(false);
    expect([...container.querySelectorAll('.evaluation-score')].every((score) => score.closest('details').open === false)).toBe(true);
    expect(container.querySelector('.preview-support').open).toBe(false);
    expect(container.querySelector('.plan-card').textContent).toContain('19:00 (València time)');
    expect(container.querySelector('.plan-card').textContent).toContain('Plaça del Mercat, València');
    expect(container.querySelector('.plan-card').textContent).toContain('ajuntament agenda');
    expect(container.querySelector('#preview-title').textContent).toContain('Thursday 22 October 2026');
    expect(document.activeElement).toBe(container.querySelector('#preview-title'));
    const other = container.querySelector('.preview-other-events');
    await act(async () => other.querySelector('summary').click());
    expect(other.open).toBe(true);
  });

  test.each([
    [{ empty: true }, "haven't found any listings", 'empty'],
    [{ empty: true, state: 'unavailable' }, 'could not check the event sources', 'unavailable'],
    [{ empty: true, state: 'partial' }, 'Some sources could not be checked', 'partial'],
    [{ filtered: true }, 'None matched your selected event types', 'filtered']
  ])('separates collection outcome %s and offers explicit recovery actions', async (options, message, result_state) => {
    const onRetry = vi.fn();
    const onEditPreferences = vi.fn();
    const onFeedback = vi.fn().mockResolvedValue(undefined);
    await renderPreview(planningPayload(options), { onRetry, onEditPreferences, onFeedback });
    expect(container.querySelector('.preview-result-message').textContent).toContain(message);
    expect(container.textContent).toContain('Thursday 22 October 2026');
    expect(container.querySelector('.preview-checked time').dateTime).toBe('2026-10-21T20:00:00Z');
    expect(container.querySelector('.plan-card')).toBeNull();
    if (options.state) expect(container.querySelector('.preview-result-message').textContent).not.toContain("haven't found any");
    await click('Check again');
    await click('Edit my choices');
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onEditPreferences).toHaveBeenCalledOnce();
    expect(onFeedback).not.toHaveBeenCalled();
    await click('Not useful');
    expect(onFeedback).toHaveBeenCalledWith({ date: '2026-10-22', result_state, useful: false, action: null });
  });

  test('never turns legacy eligible evaluations into recommendation cards', async () => {
    await renderPreview(envelope([examples.matched]));
    expect(container.querySelector('.plan-card')).toBeNull();
    expect(container.textContent).toContain('ranked shortlist is not available');
    expect(planButton('Copy shortlist')).toBeUndefined();
    expect(container.querySelector('.preview-feedback')).toBeNull();
  });

  test('copies public details only after a click and saves by canonical event ID', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const onSaveEvent = vi.fn().mockResolvedValue(undefined);
    const onFeedback = vi.fn();
    const payload = planningPayload();
    payload.plans.recommendations[0].reason = 'PRIVATE family preference reason';
    await renderPreview(payload, { onSaveEvent, onFeedback });
    expect(writeText).not.toHaveBeenCalled();
    expect(onSaveEvent).not.toHaveBeenCalled();
    expect(onFeedback).not.toHaveBeenCalled();
    await act(async () => planButton('Save plan').click());
    expect(onSaveEvent).toHaveBeenCalledWith(8);
    expect(container.querySelector('.plan-card [role="status"]').textContent).toContain('Plan saved');
    await click('Copy shortlist');
    expect(writeText).toHaveBeenCalledOnce();
    const copied = writeText.mock.calls[0][0];
    expect(copied.indexOf('Another concert')).toBeLessThan(copied.indexOf('Jazz in the garden'));
    expect(copied).not.toMatch(/PRIVATE|profile|reason|score|fixture-run|reader@example/);
    expect(onFeedback).not.toHaveBeenCalled();
    await act(async () => planButton('Copy event').click());
    expect(writeText.mock.calls[1][0]).not.toContain('Jazz in the garden');
  });

  test('announces copy and save failures without exposing raw errors', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('private provider details')) } });
    await renderPreview(planningPayload(), { onSaveEvent: vi.fn().mockRejectedValue(new Error('private SQL details')) });
    await click('Copy shortlist');
    expect(container.querySelector('[role="alert"]').textContent).toContain('could not copy');
    await act(async () => planButton('Save plan').click());
    expect(container.querySelector('.plan-card [role="alert"]').textContent).toContain('could not save');
    expect(container.textContent).not.toContain('private SQL');
    expect(container.textContent).not.toContain('private provider');
  });

  test('does not expose feedback controls without consent and permits explicit optional feedback', async () => {
    await renderPreview(planningPayload());
    expect(container.querySelector('.preview-feedback')).toBeNull();
    const result = parseDigestPreview(planningPayload(), ['live_music', 'food_drink']);
    const onFeedback = vi.fn().mockResolvedValue(undefined);
    await act(async () => root.render(<DigestPreview state={{ status: 'ready', result }} onFeedback={onFeedback} />));
    expect(onFeedback).not.toHaveBeenCalled();
    await act(async () => {
      const select = container.querySelector('.preview-feedback select');
      select.value = 'organizer';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await click('Useful');
    expect(onFeedback).toHaveBeenCalledWith({ date: '2026-10-22', result_state: 'recommendations', useful: true, action: 'organizer' });
    expect(container.querySelector('.preview-feedback [role="status"]').textContent).toContain('feedback was saved');
  });

  test('labels date-only exports and omits export actions for unverified dates', async () => {
    const payload = planningPayload();
    payload.plans.recommendations[0].time_precision = 'date';
    payload.plans.recommendations[1].time_precision = 'unverified';
    await renderPreview(payload);
    const cards = container.querySelectorAll('.plan-card');
    expect(planButton('Save date to calendar', cards[0])).toBeDefined();
    expect(cards[0].querySelector('input[type="checkbox"]')).toBeNull();
    expect(cards[0].querySelector('.plan-time').textContent).not.toContain('19:00');
    expect(planButton('Add to calendar', cards[1])).toBeUndefined();
    expect(cards[1].querySelector('.plan-time').textContent).toBe('Date and time not confirmed');
  });

  test('calendar download requires a click and includes the reminder only when chosen', async () => {
    const urls = { createObjectURL: vi.fn(() => 'blob:fixture'), revokeObjectURL: vi.fn() };
    const NativeURL = URL;
    vi.stubGlobal('URL', Object.assign(class extends NativeURL {}, urls));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.useFakeTimers();
    try {
      await renderPreview(planningPayload());
      expect(urls.createObjectURL).not.toHaveBeenCalled();
      const card = container.querySelector('.plan-card');
      expect(card.querySelector('input[type="checkbox"]').checked).toBe(false);
      await act(async () => card.querySelector('input[type="checkbox"]').click());
      await act(async () => planButton('Add to calendar', card).click());
      expect(urls.createObjectURL).toHaveBeenCalledOnce();
      expect(urls.createObjectURL.mock.calls[0][0].type).toBe('text/calendar;charset=utf-8');
      expect(card.querySelector('[role="status"]').textContent).toContain('Calendar file prepared');
      await act(async () => vi.runAllTimers());
      expect(urls.revokeObjectURL).toHaveBeenCalledWith('blob:fixture');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('saved-profile Jev previews', () => {
  test('requests the chosen date with authentication and displays the shared matched breakdown', async () => {
    const fetchMock = mockApi(() => json(envelope([examples.matched])));
    await renderApp();
    await click('See tomorrow’s plans');

    const [, options] = fetchMock.mock.calls.find(([path]) => path === '/api/digest/dry-run');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('include');
    expect(JSON.parse(options.body)).toEqual({ date: '2026-10-22' });
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(container.querySelector('.evaluation-decision').textContent).toBe('Eligible for your digest');
    expect(container.querySelector('.evaluation-score').textContent).toContain('0 of 1. Limit: 0.6');
    expect(container.querySelector('.preview-selected-types').textContent).toBe('Live musicFood & drink');
    const outer = container.querySelector('.preview-other-events');
    await act(async () => outer.querySelector('summary').click());
    const details = container.querySelector('.evaluation-details');
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
    expect(container.textContent).toContain('Your email subscription preference is paused.');
    expect(button('Resume email digest')).toBeDefined();
    await click('See tomorrow’s plans');
    expect(container.querySelector('.evaluation-decision').textContent).toBe('Eligible for your digest');
    expect(user.is_subscribed).toBe(false);
    expect(fetchMock.mock.calls.map(([path]) => path).filter((path) => !['/api/planning', '/api/billing'].includes(path))).toEqual(['/api/me', '/api/digest/dry-run']);
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
    await click('See tomorrow’s plans');
    expect(container.querySelector('.evaluation-decision').textContent).toBe(decision);
    expect(container.querySelector('.evaluation-score').textContent).toContain(score);
    if (name === 'irrelevant') expect(container.textContent).toContain('All evaluated events are irrelevant');
    if (['uncertain', 'fallback'].includes(name)) {
      expect(container.textContent).toContain('remains eligible for the usual ranking');
      expect(container.querySelector('.evaluation-score strong')).toBeNull();
    }
    if (name === 'uncertain') expect(container.querySelector('.evaluation-details').textContent).toContain('Not scored');
    if (name === 'fallback') expect(container.querySelector('.evaluation-details').textContent).toContain('unavailable');
  });

  test('distinguishes an empty collection from an all-irrelevant preview', async () => {
    mockApi(() => json(envelope([])));
    await renderApp();
    await click('See tomorrow’s plans');
    expect(container.textContent).toContain('No events found for tomorrow');
    expect(container.textContent).not.toContain('All evaluated events are irrelevant');
    expect(container.querySelector('.evaluation-card')).toBeNull();
    expect(button('See tomorrow’s plans').disabled).toBe(false);
  });

  test('shows a successful all-irrelevant preview even when no digest was rendered', async () => {
    mockApi(() => json(envelope([examples.irrelevant], { rendered_count: 0, failure_count: 0 })));
    await renderApp();
    await click('See tomorrow’s plans');
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
    await click('See tomorrow’s plans');
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
    await click('See tomorrow’s plans');
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
    await click('See tomorrow’s plans');
    expect(button('Finding plans…').disabled).toBe(true);
    expect([...container.querySelectorAll('[role="status"]')].some((status) => status.textContent.includes('Finding plans from your saved profile'))).toBe(true);
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
    await click('See tomorrow’s plans');
    const originalSignal = fetchMock.mock.calls.find(([path]) => path === '/api/digest/dry-run')[1].signal;
    await click('Edit my profile');
    expect(originalSignal.aborted).toBe(true);
    expect(container.querySelector('.digest-preview')).toBeNull();
    await click('Edit event types');
    const foodIndex = INTEREST_CLUSTERS.findIndex((type) => type.name === 'food_drink');
    await act(async () => container.querySelectorAll('#interests-fieldset input')[foodIndex].click());
    await submit(); // interests -> account and review
    await submit(); // save, deliberately held open
    expect(button('Saving…').disabled).toBe(true);
    expect(button('See tomorrow’s plans')).toBeUndefined();
    expect(response).toHaveBeenCalledTimes(1);
    const savedBody = JSON.parse(fetchMock.mock.calls.find(([path]) => path === '/api/preferences')[1].body);
    const savedProfile = JSON.parse(savedBody.preferences_blob);
    expect(Object.keys(savedProfile)).toHaveLength(6);
    expect(savedProfile.top_interest_clusters.map((type) => type.name)).toEqual(['live_music']);

    await act(async () => save.resolve(json({ user })));
    await click('See tomorrow’s plans');
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
    await click('See tomorrow’s plans');
    await click('Sign out');
    await act(async () => pending.resolve(json(envelope([examples.matched]))));
    expect(container.querySelector('input[name="audience"]:checked')).toBeNull();
    expect(container.querySelector('.digest-preview')).toBeNull();
    expect(container.textContent).not.toContain(examples.matched.event.title);
  });

  test('an expired session returns to sign-in and never exposes an old preview', async () => {
    const response = vi.fn().mockImplementationOnce(() => json(envelope([examples.matched])))
      .mockImplementationOnce(() => json({ error: 'No session' }, 401));
    mockApi(response);
    await renderApp();
    await click('See tomorrow’s plans');
    expect(container.querySelector('.evaluation-card')).not.toBeNull();
    await click('See tomorrow’s plans');
    expect(container.textContent).toContain('Your session has expired');
    expect(button('Email me a sign-in link')).toBeDefined();
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
    await act(async () => container.querySelector('input[name="audience"]').click());
    await submit();
    await act(async () => container.querySelector('#interests-fieldset input').click());
    await submit();
    await submit();
    await act(async () => {
      const email = container.querySelector('#email');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(email, user.email);
      email.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await submit();
    expect(container.textContent).toContain('One quick step remains');
    expect(button('See tomorrow’s plans')).toBeUndefined();
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/api/me', '/api/register']);
  });

  test('requires review of unsupported saved selections instead of silently previewing defaults', async () => {
    const profile = JSON.parse(user.preferences_blob);
    profile.top_interest_clusters.push({ name: 'unknown_saved_type', includes: [] });
    user.preferences_blob = JSON.stringify(profile);
    const fetchMock = mockApi(() => json(envelope([examples.matched])));
    await renderApp();
    await click('See tomorrow’s plans');
    expect(container.querySelector('[role="alert"]').textContent).toContain('Edit and save your profile');
    expect(fetchMock.mock.calls.map(([path]) => path).filter((path) => !['/api/planning', '/api/billing'].includes(path))).toEqual(['/api/me']);
    expect(button('Retry preview')).toBeUndefined();
  });

  test('renders event titles as text and only links to validated web URLs', async () => {
    const evaluation = structuredClone(examples.matched);
    evaluation.event.title = '<img src=x onerror=alert(1)>';
    mockApi(() => json(envelope([evaluation])));
    await renderApp();
    await click('See tomorrow’s plans');
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
    await click('See tomorrow’s plans');
    expect(container.querySelector('[role="alert"]').textContent).toContain('could not read this preview safely');
    expect(container.querySelector('.evaluation-card')).toBeNull();
    expect(button('Retry preview')).toBeDefined();
  });
});
