// @vitest-environment jsdom
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import PlanningTools from '../pages/src/PlanningTools.jsx';

const event = { id: 1, event_key: 'film', title: 'A public film', url: 'https://example.com/film', start_at: '2026-10-24T18:00:00+02:00', end_at: null, time_precision: 'datetime', location: '', description: '', source: 'fixture' };
const planning = () => ({ version: 'brisa-planning-v1', today: '2026-10-21', available_dates: Array.from({ length: 7 }, (_, i) => `2026-10-${22 + i}`), delivery_enabled: false, delivery_days: [0, 1, 2, 3, 4, 5, 6], subscribed: true, saved_events: [event], pilot: { consented: false, expires_at: null }, coverage_history: [] });
const membership = () => ({ available: false, livemode: false, price_eur: 3, interval: 'month', status: 'none', active: false, can_manage: false, cancel_at_period_end: false, current_period_end: 0 });
const json = (value, status = 200) => new Response(JSON.stringify(value), { status });
let container, root, api, data, billing, props;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.history.replaceState({}, '', '/');
  container = document.createElement('div'); document.body.append(container);
  data = planning(); billing = membership();
  props = { user: { id: 1, email: 'private@example.com', is_subscribed: true }, onPlanningChange: vi.fn(), onUserChange: vi.fn(), navigate: vi.fn() };
  api = vi.fn(async (path, options = {}) => {
    if (path === '/api/planning') return json(data);
    if (path === '/api/billing') return json({ membership: billing });
    if (path === '/api/planning/saved') return json({ saved_events: [] });
    if (path === '/api/planning/delivery') { const payload = JSON.parse(options.body); return json({ delivery_days: payload.days, subscribed: payload.subscribed }); }
    if (path === '/api/planning/pilot') return json({ pilot: { consented: true, expires_at: '2026-11-20T20:00:00+00:00' } });
    if (path === '/api/billing/checkout') return json({ url: 'https://checkout.stripe.com/c/pay/example' });
    throw new Error('Unexpected route: ' + path);
  });
  vi.stubGlobal('fetch', api);
});
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function render(next = props) { await act(async () => { root ||= createRoot(container); root.render(<PlanningTools {...next} />); }); }
async function click(text) { const target = [...container.querySelectorAll('button')].find((button) => button.textContent === text); expect(target).toBeDefined(); await act(async () => target.click()); }

test('shows honest service state and explicit opt-in without passive feedback', async () => {
  await render();
  expect(container.textContent).toContain('Email delivery is currently off');
  expect(container.textContent).toContain('Paid membership is not open yet');
  expect(props.onPlanningChange).toHaveBeenLastCalledWith(data);
  expect(api.mock.calls.every(([path]) => !path.includes('feedback'))).toBe(true);
  await click('Join the optional feedback pilot');
  expect(props.onPlanningChange.mock.lastCall[0].pilot.consented).toBe(true);
});

test('copies only public shortlist data and removes only the chosen event', async () => {
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  await render(); await click('Copy household shortlist');
  expect(writeText.mock.calls[0][0]).toContain('https://example.com/film');
  expect(writeText.mock.calls[0][0]).not.toContain('private@example.com');
  await click('Remove');
  expect(JSON.parse(api.mock.calls.find(([path]) => path.endsWith('/saved'))[1].body)).toEqual({ event_id: 1 });
  expect(container.textContent).toContain('No saved events yet');
});

test('schedule changes require a save and propagate subscription state', async () => {
  await render();
  const box = [...container.querySelectorAll('input')].find((input) => input.parentElement.textContent.includes('Keep my email'));
  await act(async () => box.click());
  expect(api.mock.calls.some(([path]) => path.endsWith('/delivery'))).toBe(false);
  await click('Save delivery preferences');
  expect(props.onUserChange).toHaveBeenLastCalledWith({ ...props.user, is_subscribed: false });
  expect(container.textContent).toContain('Preferences saved. Email delivery is currently off.');
});

test.each([{ coverage_history: [null] }, { saved_events: [{ ...event, url: 'javascript:alert(1)' }] }])('invalid planning data fails safely: %j', async (change) => {
  Object.assign(data, change); await render();
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
  expect(props.onPlanningChange).toHaveBeenLastCalledWith(null);
  expect(container.textContent).not.toContain('A public film');
});

test('billing response must validate booleans before showing active membership', async () => {
  billing.available = true; billing.active = 'false'; await render();
  expect(container.textContent).not.toContain('Your membership is active');
  expect(container.textContent).toContain('Membership status is unavailable');
});

test('checkout is explicit and uses server-hosted redirect', async () => {
  billing.available = true; await render();
  expect(props.navigate).not.toHaveBeenCalled();
  await click('Open test checkout');
  expect(props.navigate).toHaveBeenCalledWith('https://checkout.stripe.com/c/pay/example');
});

test('checkout return does not grant membership', async () => {
  window.history.replaceState({}, '', '/?billing=success'); await render();
  expect(container.textContent).toContain('waiting for confirmed billing status');
  expect(container.textContent).not.toContain('Your membership is active');
});

test('stale account responses never replace the current account', async () => {
  let resolveOld;
  api.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
  await render();
  data = { ...planning(), saved_events: [] };
  await render({ ...props, user: { ...props.user, id: 2 } });
  await act(async () => resolveOld(json(planning())));
  expect(container.textContent).toContain('No saved events yet');
  expect(container.textContent).not.toContain('A public film');
});

test('successful refresh preserves parent dates instead of emitting null', async () => {
  await render(); props.onPlanningChange.mockClear();
  await render({ ...props, refreshKey: 1 });
  expect(props.onPlanningChange.mock.calls.every(([value]) => value !== null)).toBe(true);
});
