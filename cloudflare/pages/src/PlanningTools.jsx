import { useEffect, useRef, useState } from 'react';
import { apiFetch } from './api.js';
import { canExportCalendar, calendarFilename, eventCalendar, eventTimeLabel, shortlistCopyText, validPublicEvent, validDate, validTimestamp } from './planning.js';
import './planning.css';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const STATUSES = ['none', 'active', 'trialing', 'past_due', 'unpaid', 'paused', 'incomplete', 'incomplete_expired', 'canceled'];

function validPilot(pilot) {
  return typeof pilot?.consented === 'boolean' && (pilot.consented ? validTimestamp(pilot.expires_at) : pilot.expires_at === null);
}

function validMembership(value) {
  return value && ['available', 'active', 'can_manage', 'livemode', 'cancel_at_period_end'].every((key) => typeof value[key] === 'boolean') &&
    value.price_eur === 3 && value.interval === 'month' && STATUSES.includes(value.status) &&
    value.active === ['active', 'trialing'].includes(value.status) &&
    Number.isSafeInteger(value.current_period_end) && value.current_period_end >= 0;
}

function validCoverage(row) {
  return row && typeof row.source === 'string' && row.source.length <= 80 &&
    validDate(row.checked_date) && validTimestamp(row.checked_at) && ['ok', 'error'].includes(row.status) &&
    ['fetched_count', 'event_count'].every((key) => Number.isSafeInteger(row[key]) && row[key] >= 0);
}

function validPlanning(data) {
  return data?.version === 'brisa-planning-v1' && validDate(data.today) &&
    Array.isArray(data.available_dates) && data.available_dates.length === 7 && data.available_dates.every(validDate) &&
    typeof data.delivery_enabled === 'boolean' && typeof data.subscribed === 'boolean' &&
    Array.isArray(data.delivery_days) && data.delivery_days.every((day) => Number.isInteger(day) && day >= 0 && day < 7) &&
    new Set(data.delivery_days).size === data.delivery_days.length &&
    Array.isArray(data.saved_events) && data.saved_events.length <= 50 && data.saved_events.every(validPublicEvent) &&
    validPilot(data.pilot) && Array.isArray(data.coverage_history) && data.coverage_history.length <= 40 && data.coverage_history.every(validCoverage);
}

export function downloadCalendar(event) {
  const blob = new Blob([eventCalendar(event)], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = calendarFilename(event);
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

export default function PlanningTools({ user, onUserChange, onPlanningChange, refreshKey = 0, navigate = (url) => window.location.assign(url) }) {
  const [data, setData] = useState(null);
  const [membership, setMembership] = useState(null);
  const [days, setDays] = useState([]);
  const [subscribed, setSubscribed] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  const callbacks = useRef({ onUserChange, onPlanningChange });
  callbacks.current = { onUserChange, onPlanningChange };

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    setLoading(true); setData(null); setMembership(null); setError(''); setNotice(''); setBusy(false);
    Promise.allSettled([
      apiFetch('/api/planning', { signal: controller.signal }),
      apiFetch('/api/billing', { signal: controller.signal })
    ]).then(([planningResult, billingResult]) => {
      if (current !== generation.current || controller.signal.aborted) return;
      if (planningResult.status === 'fulfilled' && validPlanning(planningResult.value)) {
        const value = planningResult.value;
        setData(value); setDays(value.delivery_days); setSubscribed(value.subscribed);
        callbacks.current.onPlanningChange?.(value);
      } else {
        callbacks.current.onPlanningChange?.(null);
        setError('Your saved plans and settings could not be loaded. Please retry.');
      }
      if (billingResult.status === 'fulfilled' && validMembership(billingResult.value?.membership)) {
        setMembership(billingResult.value.membership);
      }
      setLoading(false);
    });
    return () => { controller.abort(); generation.current += 1; };
  }, [user.id, refreshKey, reload]);

  async function perform(action) {
    const current = generation.current;
    setBusy(true); setError(''); setNotice('');
    try {
      await action(() => current === generation.current);
    } catch (failure) {
      if (current === generation.current) setError(failure.message || 'That change could not be saved. Please retry.');
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }

  function replaceData(next) {
    setData(next); callbacks.current.onPlanningChange?.(next);
  }

  async function saveSchedule(event) {
    event.preventDefault();
    await perform(async (current) => {
      const result = await apiFetch('/api/planning/delivery', { method: 'PATCH', body: JSON.stringify({ days, subscribed }) });
      if (!current()) return;
      const next = { ...data, delivery_days: result.delivery_days, subscribed: result.subscribed };
      if (!validPlanning(next)) throw new Error('Delivery preferences could not be confirmed. Please refresh.');
      replaceData(next);
      callbacks.current.onUserChange?.({ ...user, is_subscribed: result.subscribed });
      setNotice(data.delivery_enabled ? 'Delivery preferences saved.' : 'Preferences saved. Email delivery is currently off.');
    });
  }

  async function consent(value) {
    await perform(async (current) => {
      const result = await apiFetch('/api/planning/pilot', { method: 'PUT', body: JSON.stringify({ consented: value }) });
      if (!current()) return;
      if (!validPilot(result.pilot)) throw new Error('Feedback consent could not be confirmed. Please refresh.');
      replaceData({ ...data, pilot: result.pilot });
      setNotice(value ? 'Feedback participation enabled for 30 days. Every response is optional.' : 'Participation stopped and your pilot feedback deleted.');
    });
  }

  async function remove(eventId) {
    await perform(async (current) => {
      const result = await apiFetch('/api/planning/saved', { method: 'DELETE', body: JSON.stringify({ event_id: eventId }) });
      if (!current()) return;
      if (!Array.isArray(result.saved_events) || !result.saved_events.every(validPublicEvent)) throw new Error('Saved plans could not be read. Please refresh.');
      replaceData({ ...data, saved_events: result.saved_events }); setNotice('Event removed from your shortlist.');
    });
  }

  async function billing(action) {
    await perform(async (current) => {
      const result = await apiFetch('/api/billing/' + action, { method: 'POST' });
      if (!current()) return;
      const url = new URL(result.url);
      const host = action === 'portal' ? 'billing.stripe.com' : 'checkout.stripe.com';
      if (url.protocol !== 'https:' || url.host !== host || url.username || url.password) throw new Error('The secure payment link could not be opened.');
      navigate(url.href);
    });
  }

  return <section className="planning-tools" aria-label="Your planning tools">
    {loading ? <p role="status">Loading your saved plans and settings…</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {notice ? <p className="plan-status" role="status">{notice}</p> : null}
    {!loading && !data ? <button type="button" onClick={() => setReload((value) => value + 1)}>Retry planning settings</button> : null}
    {data ? <>
      <section className="saved-plans" aria-labelledby="saved-plans-title">
        <h2 id="saved-plans-title">Your saved plans</h2>
        <p>Keep up to 50 events here. A shared shortlist includes only public titles, dates and event links.</p>
        {data.saved_events.length ? <>
          <button type="button" disabled={busy} onClick={() => perform(async (current) => {
            if (!navigator.clipboard?.writeText) throw new Error('Copy is unavailable in this browser. You can use each event’s public link.');
            await navigator.clipboard.writeText(shortlistCopyText(data.saved_events));
            if (current()) setNotice('Public shortlist copied. You can share it with your household.');
          })}>Copy household shortlist</button>
          <ul className="plan-list">{data.saved_events.map((event) => <li className="plan-card" key={event.id}>
            <h3><a href={event.url} target="_blank" rel="noopener noreferrer">{event.title}</a></h3>
            <p className="plan-facts">{eventTimeLabel(event)}</p>
            {event.location ? <p>{event.location}</p> : null}
            <div className="plan-actions">
              {canExportCalendar(event) ? <button type="button" disabled={busy} onClick={() => perform(async (current) => {
                downloadCalendar(event); if (current()) setNotice('Calendar file downloaded. Confirm the details with the organiser.');
              })}>{event.time_precision === 'date' ? 'Save the date' : 'Add to calendar'}</button> : null}
              <button type="button" disabled={busy} onClick={() => remove(event.id)} aria-label={'Remove ' + event.title}>Remove</button>
            </div>
          </li>)}</ul>
        </> : <p>No saved events yet. Save a suggestion from your plans to build a shortlist.</p>}
      </section>

      <details className="planning-settings"><summary>Email preferences</summary>
        <p>{data.delivery_enabled ? 'Choose which event days you want a digest for. We send the day before.' : 'Email delivery is currently off. These choices will apply when it becomes available; previews work now.'}</p>
        <form onSubmit={saveSchedule}>
          <fieldset disabled={busy}><legend>Days you want plans for</legend>
            <div className="delivery-days">{DAYS.map((label, day) => <label key={day}>
              <input type="checkbox" checked={days.includes(day)} onChange={(event) => setDays(event.target.checked ? [...days, day].sort() : days.filter((value) => value !== day))} />{label}
            </label>)}</div>
            <label><input type="checkbox" checked={subscribed} onChange={(event) => setSubscribed(event.target.checked)} /> Keep my email subscription active</label>
          </fieldset>
          <button type="submit" disabled={busy || (subscribed && days.length === 0)}>Save delivery preferences</button>
        </form>
      </details>

      <details className="planning-settings"><summary>Source coverage</summary>
        <p>These checks show what the current sources returned. A successful check does not mean we found every event in València. Coverage beyond the city is not established.</p>
        {data.coverage_history.length ? <div className="coverage-table"><table><caption>Recent public source checks</caption>
          <thead><tr><th>Source</th><th>Event day</th><th>Result</th><th>Checked</th></tr></thead>
          <tbody>{data.coverage_history.slice(0, 40).map((row, index) => <tr key={index}>
            <td>{String(row.source).replaceAll('_', ' ')}</td><td>{row.checked_date}</td>
            <td>{row.status === 'ok' ? `${row.event_count} listings` : 'Unavailable'}</td>
            <td>{Number.isFinite(Date.parse(row.checked_at)) ? new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Madrid', dateStyle: 'short', timeStyle: 'short' }).format(new Date(row.checked_at)) : 'Time unavailable'}</td>
          </tr>)}</tbody></table></div> : <p>No source checks recorded yet. Check a date to see current coverage.</p>}
      </details>

      <details className="planning-settings"><summary>Help improve Brisa</summary>
        <p>Join an optional 30-day feedback pilot. If you choose to respond, we store the day, result state, whether it was useful, and any action you explicitly report. No event names or profile choices are included. A random study code is linked separately to your account.</p>
        <p>We delete the link and feedback after 30 days, or when you stop participating. Opening event links does not send feedback.</p>
        <button type="button" disabled={busy} onClick={() => consent(!data.pilot.consented)}>{data.pilot.consented ? 'Stop participating and delete feedback' : 'Join the optional feedback pilot'}</button>
      </details>
    </> : null}

    {!loading ? <section className="membership-card" aria-labelledby="membership-title">
      <h2 id="membership-title">Brisa membership</h2>
      <p>Support the continued development of Brisa for €3 per month. Planning tools are available during beta; membership does not include event tickets or guarantee daily listings.</p>
      {new URLSearchParams(window.location.search).get('billing') === 'success' && !membership?.active ? <p role="status">Checkout returned. We are waiting for confirmed billing status; this page alone does not confirm payment.</p> : null}
      {new URLSearchParams(window.location.search).get('billing') === 'cancelled' ? <p>Checkout was cancelled. You can keep using Brisa.</p> : null}
      {!membership ? <p>Membership status is unavailable. Please refresh to check it.</p>
        : <>
          {membership.active ? <p role="status">Your membership is active{membership.cancel_at_period_end ? ' and will end after the current paid period' : ''}. Thank you for supporting Brisa.</p> : null}
          {membership.status && !['none', 'active', 'trialing', 'canceled', 'incomplete_expired'].includes(membership.status) ? <p>Your membership needs attention. Open billing to check payment details.</p> : null}
          {!membership.available ? <p>Paid membership is not open yet.</p> : !membership.active && !membership.can_manage ? <>
            {!membership.livemode ? <p>This is a test checkout. No live payments are accepted.</p> : null}
            <p>Renews monthly. Manage or cancel through Stripe. The final amount and billing details are shown before payment.</p>
            <button type="button" disabled={busy} onClick={() => billing('checkout')}>{membership.livemode ? 'Continue to secure checkout · €3/month' : 'Open test checkout'}</button>
          </> : null}
          {membership.can_manage ? <>
            <button type="button" disabled={busy} onClick={() => billing('portal')}>Manage billing and cancellation</button>
            {membership.available && ['none', 'canceled', 'incomplete_expired'].includes(membership.status) ? <button type="button" disabled={busy} onClick={() => billing('checkout')}>{membership.livemode ? 'Start membership · €3/month' : 'Open test checkout'}</button> : null}
          </> : null}
        </>}
      <button type="button" className="text-button" disabled={busy} onClick={() => setReload((value) => value + 1)}>Refresh account status</button>
    </section> : null}
  </section>;
}
