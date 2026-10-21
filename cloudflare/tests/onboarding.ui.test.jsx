// @vitest-environment jsdom

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import App from '../pages/src/App.jsx';
import { DEFAULT_FORM_STATE, INTEREST_CLUSTERS, buildPersonalizationProfile } from '../pages/src/profile.js';

const planningStub = vi.hoisted(() => ({ data: null, props: null }));
const previewBoundary = vi.hoisted(() => ({ props: null }));
vi.mock('../pages/src/DigestPreview.jsx', async (importOriginal) => {
  const { default: DigestPreview } = await importOriginal();
  return { default: function PreviewBoundary(props) {
    previewBoundary.props = props;
    return <DigestPreview {...props} />;
  } };
});
vi.mock('../pages/src/PlanningTools.jsx', async () => {
  const { useEffect } = await import('react');
  return {
    default: function PlanningToolsStub(props) {
      planningStub.props = props;
      useEffect(() => {
        let active = true;
        Promise.resolve().then(() => { if (active) props.onPlanningChange(planningStub.data); });
        return () => { active = false; };
      }, [props.onPlanningChange, props.refreshKey]);
      return <div data-testid="planning-tools" />;
    }
  };
});

let container;
let root;

function response(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } });
}

function button(label) {
  return [...container.querySelectorAll('button')].find((item) => item.textContent === label || item.getAttribute('aria-label') === label);
}

async function inputValue(input, value) {
  await act(async () => {
    const prototype = input instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event(input instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
  });
}

async function next() {
  await act(async () => container.querySelector('form').requestSubmit());
}

async function chooseAudience(value = 'solo_adult') {
  await act(async () => container.querySelector(`input[name="audience"][value="${value}"]`).click());
}

async function chooseType(name) {
  const index = INTEREST_CLUSTERS.findIndex((option) => option.name === name);
  await act(async () => container.querySelectorAll('#interests-fieldset input')[index].click());
}

function user(overrides = {}) {
  return {
    id: 7, email: 'reader@example.com', is_active: true, is_subscribed: true,
    preferences_blob: JSON.stringify(buildPersonalizationProfile({
      ...DEFAULT_FORM_STATE, audience: 'solo_adult', interests: ['film']
    })),
    ...overrides
  };
}

const planningData = {
  version: 'brisa-planning-v1', today: '2026-10-21',
  available_dates: ['2026-10-22', '2026-10-23', '2026-10-24', '2026-10-25', '2026-10-26', '2026-10-27', '2026-10-28'],
  delivery_enabled: false, pilot: { consented: false }
};

function legacyPreview(reference, date) {
  return {
    summary: { correlation_id: reference, dry_run: true, event_count: 1, rendered_count: 1, sent_count: 0, failure_count: 0, ...(date ? { digest_date: date } : {}) }
  };
}

async function renderApp() {
  await act(async () => {
    root = createRoot(container);
    root.render(<App />);
  });
}

async function reachReview() {
  await renderApp();
  await chooseAudience();
  await next();
  await chooseType('film');
  await next();
  await act(async () => button('Skip optional refinements').click());
}

async function completeProfile(emailAddress = 'reader@example.com') {
  await reachReview();
  await inputValue(container.querySelector('#email'), emailAddress);
  await next();
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.history.replaceState({}, '', '/');
  planningStub.data = null;
  planningStub.props = null;
  previewBoundary.props = null;
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
  test('requires an explicit audience and explains actual coverage before account details', async () => {
    await renderApp();
    expect(container.querySelectorAll('input[type="radio"]:checked')).toHaveLength(0);
    expect(container.querySelector('#email')).toBeNull();
    expect(container.querySelectorAll('#locations-fieldset input')).toHaveLength(1);
    expect(container.querySelector('#coverage-hint').textContent).toContain('do not yet promise');
    await next();
    const fieldset = container.querySelector('#audience-fieldset');
    expect(document.activeElement).toBe(fieldset);
    expect(fieldset.getAttribute('aria-describedby')).toBe('audience-error');
    await chooseAudience('family_with_school_age_kids');
    await next();
    expect(container.querySelectorAll('#interests-fieldset input:checked')).toHaveLength(0);
  });

  test('waits for email verification after the register API accepts a new profile', async () => {
    fetch.mockImplementation(async (path) => new Response(
      JSON.stringify(path === '/api/register'
        ? { ok: true, message: 'Check your email to continue' }
        : { error: 'No session' }),
      { status: path === '/api/register' ? 202 : 401 }
    ));

    await completeProfile();

    expect(container.querySelector('h2').textContent).toBe('One quick step remains.');
    expect(container.textContent).toContain('reader@example.com');
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('button')?.textContent).not.toContain('Preview');
    const registration = fetch.mock.calls.find(([path]) => path === '/api/register');
    const saved = JSON.parse(JSON.parse(registration[1].body).preferences_blob);
    expect(saved).toMatchObject({
      audience: 'solo_adult', strong_positive_signals: [], strong_negative_signals: [], seasonal_anchors: []
    });
    expect(saved.top_interest_clusters.map(({ name }) => name)).toEqual(['film']);
  });

  test('offers sign-in at review when the email already has an account', async () => {
    fetch.mockImplementation(async (path) => new Response(
      JSON.stringify(path === '/api/register'
        ? { error: 'User already exists' }
        : path === '/api/login'
          ? { ok: true, message: 'Check your email to continue' }
          : { error: 'No session' }),
      { status: path === '/api/register' ? 409 : path === '/api/login' ? 202 : 401 }
    ));

    await completeProfile();

    const signIn = [...container.querySelectorAll('button')]
      .find((button) => button.textContent === 'Email me a sign-in link');
    expect(signIn).toBeDefined();
    await act(async () => signIn.click());
    const loginRequest = fetch.mock.calls.find(([path]) => path === '/api/login');
    expect(JSON.parse(loginRequest[1].body)).toEqual({ email: 'reader@example.com' });
    expect(container.querySelector('h2').textContent).toBe('One quick step remains.');
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  test('supports bounded multi-selection, required validation, and back navigation', async () => {
    await renderApp();
    await chooseAudience();
    await next();

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
    await reachReview();

    await act(async () => container.querySelector('form').requestSubmit());

    const email = container.querySelector('#email');
    expect(email.getAttribute('aria-invalid')).toBe('true');
    expect(email.getAttribute('aria-describedby')).toContain('email-error');
    expect(container.querySelector('#email-error').textContent).toBe('Enter a valid email address.');
    expect(document.activeElement).toBe(email);
  });

  test('supports form submission and focuses the next step heading', async () => {
    await renderApp();
    await chooseAudience();
    await next();

    const heading = container.querySelector('#step-title');
    expect(heading.textContent).toBe('Which events interest you?');
    expect(document.activeElement).toBe(heading);
    expect(container.querySelector('[role="progressbar"]').getAttribute('aria-valuenow')).toBe('2');
    expect(container.querySelector('[role="progressbar"]').getAttribute('aria-valuemax')).toBe('4');
  });

  test('lets returning visitors request access without filling new preferences', async () => {
    fetch.mockImplementation(async (path) => path === '/api/login' ? response({ ok: true }, 202) : response({ error: 'No session' }, 401));
    await renderApp();
    await act(async () => button('Already registered? Sign in').click());
    await inputValue(container.querySelector('#email'), 'returning@example.com');
    await next();
    expect(fetch.mock.calls.filter(([path]) => path === '/api/login')).toHaveLength(1);
    expect(fetch.mock.calls.some(([path]) => path === '/api/register')).toBe(false);
    expect(container.querySelector('h2').textContent).toBe('One quick step remains.');
  });

  test('shows actual preference labels and returns section edits directly to review', async () => {
    const savedForm = {
      ...DEFAULT_FORM_STATE, audience: 'family_with_school_age_kids',
      locations: ['Valencia city', 'Valencia metro area'], interests: ['film', 'parks_and_play'],
      positiveSignals: ['daytime', 'near_transit'], negativeSignals: ['starts_after_20'],
      seasonalAnchors: ['Fallas']
    };
    const savedUser = user({ preferences_blob: JSON.stringify(buildPersonalizationProfile(savedForm)) });
    fetch.mockImplementation(async (path, options) => {
      if (path === '/api/me') return response({ user: savedUser });
      if (path === '/api/preferences') return response({ user: { ...savedUser, preferences_blob: JSON.parse(options.body).preferences_blob } });
      return response({ error: 'Not found' }, 404);
    });
    await renderApp();
    await act(async () => button('Edit my profile').click());
    expect(container.querySelector('.review-card').textContent).toContain('Daytime, Near public transit');
    expect(container.querySelector('.review-card').textContent).toContain('Starts after 20:00');
    expect(container.querySelector('.review-card').textContent).toContain('Fallas');
    expect(container.querySelector('.review-card').textContent).toContain('Metro area');
    await act(async () => button('Edit audience').click());
    expect(container.querySelector('#coverage-hint')).not.toBeNull();
    expect(container.querySelectorAll('#locations-fieldset input:checked')).toHaveLength(2);
    const metro = container.querySelectorAll('#locations-fieldset input')[1];
    await act(async () => metro.click());
    expect(container.querySelectorAll('#locations-fieldset input')).toHaveLength(2);
    await act(async () => metro.click());
    await chooseAudience('couple');
    await next();
    expect(container.querySelector('#step-title').textContent).toBe('Save your choices.');
    expect(container.querySelector('.review-card').textContent).toContain('Two of us');
    await next();
    const submitted = JSON.parse(JSON.parse(fetch.mock.calls.find(([path]) => path === '/api/preferences')[1].body).preferences_blob);
    expect(submitted).toEqual({ ...buildPersonalizationProfile(savedForm), audience: 'couple' });
    expect(container.querySelector('.next-button').textContent).toBe('See tomorrow’s plans');
  });
});

describe('account planning integration', () => {
  test('uses server dates and delivery state, with weekend and next-week shortcuts', async () => {
    planningStub.data = planningData;
    fetch.mockImplementation(async (path, options) => response(path === '/api/me' ? { user: user() } : legacyPreview('dated-preview', JSON.parse(options.body).date)));
    await renderApp();
    expect(container.querySelector('.planning-service-state').textContent).toContain('Email delivery has not started yet');
    expect(container.querySelector('.planning-local-date').textContent).toContain('Wednesday 21 October');
    expect([...container.querySelectorAll('#plan-date option')].map((option) => option.value)).toEqual(planningData.available_dates);
    await act(async () => button('This weekend').click());
    expect(container.querySelector('#plan-date').value).toBe('2026-10-24');
    await act(async () => container.querySelector('.next-button').click());
    const request = fetch.mock.calls.find(([path]) => path === '/api/digest/dry-run');
    expect(JSON.parse(request[1].body)).toEqual({ date: '2026-10-24' });
    expect(container.querySelector('.preview-error')).toBeNull();
    await act(async () => button('Next Monday').click());
    expect(container.querySelector('#plan-date').value).toBe('2026-10-26');
  });

  test('cancels a date-specific request and discards its late response after a date change', async () => {
    planningStub.data = planningData;
    let finishPreview;
    fetch.mockImplementation(async (path) => path === '/api/me'
      ? response({ user: user() })
      : new Promise((resolve) => { finishPreview = resolve; }));
    await renderApp();
    await act(async () => button('See tomorrow’s plans').click());
    const request = fetch.mock.calls.find(([path]) => path === '/api/digest/dry-run');
    await inputValue(container.querySelector('#plan-date'), '2026-10-25');
    expect(request[1].signal.aborted).toBe(true);
    await act(async () => finishPreview(response(legacyPreview('stale-date-response'))));
    expect(container.textContent).not.toContain('stale-date-response');
    expect(container.querySelector('.next-button').disabled).toBe(false);
    expect(container.querySelector('.next-button').textContent).toContain('Sunday 25 October');
  });

  test('keeps tomorrow previews working when account planning is unavailable', async () => {
    fetch.mockImplementation(async (path) => response(path === '/api/me' ? { user: user() } : legacyPreview('legacy-preview')));
    await renderApp();
    expect(container.querySelector('#plan-date')).toBeNull();
    expect(container.querySelector('.planning-service-state').textContent).toContain('Email delivery status is unavailable');
    await act(async () => button('See tomorrow’s plans').click());
    const request = fetch.mock.calls.find(([path]) => path === '/api/digest/dry-run');
    expect(request[1].body).toBeUndefined();
    expect(container.querySelector('.preview-error')).toBeNull();
  });

  test.each([undefined, '2026-10-22'])('does not label a response for %s as the chosen future day', async (responseDate) => {
    planningStub.data = planningData;
    fetch.mockImplementation(async (path) => response(path === '/api/me' ? { user: user() } : legacyPreview('wrong-day-preview', responseDate)));
    await renderApp();
    await act(async () => button('This weekend').click());
    await act(async () => container.querySelector('.next-button').click());
    expect(container.querySelector('.preview-error').textContent).toContain('does not confirm the selected day');
    expect(container.textContent).not.toContain('wrong-day-preview');
  });

  test('refreshes account planning after pausing without claiming delivery started', async () => {
    planningStub.data = planningData;
    fetch.mockImplementation(async (path, options) => response({ user: user({
      is_subscribed: path === '/api/subscription' ? JSON.parse(options.body).subscribed : true
    }) }));
    await renderApp();
    const initialKey = planningStub.props.refreshKey;
    await act(async () => button('Pause email digest').click());
    expect(planningStub.props.refreshKey).toBe(initialKey + 1);
    expect(button('Resume email digest')).toBeDefined();
    expect(container.querySelector('.planning-service-state').textContent).toContain('Email delivery has not started yet');
    expect(button('See tomorrow’s plans')).toBeDefined();
  });

  test.each(['saved profile', 'sign-out'])('discards a pending preview when %s changes', async (change) => {
    planningStub.data = planningData;
    let finishPreview;
    fetch.mockImplementation(async (path) => {
      if (path === '/api/me') return response({ user: user() });
      if (path === '/api/logout') return response({ ok: true });
      return new Promise((resolve) => { finishPreview = resolve; });
    });
    await renderApp();
    await act(async () => button('See tomorrow’s plans').click());
    const request = fetch.mock.calls.find(([path]) => path === '/api/digest/dry-run');
    await act(async () => {
      if (change === 'sign-out') button('Sign out').click();
      else planningStub.props.onUserChange(user({ preferences_blob: JSON.stringify(buildPersonalizationProfile({
        ...DEFAULT_FORM_STATE, audience: 'solo_adult', interests: ['live_music']
      })) }));
    });
    expect(request[1].signal.aborted).toBe(true);
    await act(async () => finishPreview(response(legacyPreview('stale-account-response'))));
    expect(container.textContent).not.toContain('stale-account-response');
  });

  test('offers feedback only after consent, and sends only explicitly submitted fields', async () => {
    planningStub.data = planningData;
    fetch.mockImplementation(async (path) => response(path === '/api/me' ? { user: user() } : { ok: true }));
    await renderApp();
    expect(previewBoundary.props.onFeedback).toBeUndefined();
    expect(fetch.mock.calls.some(([path]) => path === '/api/planning/feedback')).toBe(false);
    await act(async () => planningStub.props.onPlanningChange({ ...planningData, pilot: { consented: true } }));
    expect(typeof previewBoundary.props.onFeedback).toBe('function');
    await act(async () => previewBoundary.props.onFeedback({
      date: '2026-10-22', result_state: 'recommendations', useful: true, action: null,
      email: 'private@example.com', event_title: 'Do not send', preferences_blob: 'private'
    }));
    const request = fetch.mock.calls.find(([path]) => path === '/api/planning/feedback');
    expect(JSON.parse(request[1].body)).toEqual({
      date: '2026-10-22', result_state: 'recommendations', useful: true, action: null
    });
  });

  test('saving a plan posts its canonical ID and refreshes the saved-plan panel', async () => {
    planningStub.data = planningData;
    fetch.mockImplementation(async (path) => response(path === '/api/me' ? { user: user() } : { saved_events: [] }));
    await renderApp();
    const initialKey = planningStub.props.refreshKey;
    expect(fetch.mock.calls.some(([path]) => path === '/api/planning/saved')).toBe(false);
    await act(async () => previewBoundary.props.onSaveEvent(17));
    const request = fetch.mock.calls.find(([path]) => path === '/api/planning/saved');
    expect(JSON.parse(request[1].body)).toEqual({ event_id: 17 });
    expect(planningStub.props.refreshKey).toBe(initialKey + 1);
  });
});
