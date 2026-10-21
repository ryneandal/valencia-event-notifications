import { useEffect, useRef, useState } from 'react';

import { eventTypeLabel } from './preview.js';
import {
  calendarFilename, canExportCalendar, directionsUrl, eventCalendar,
  eventCopyText, eventTimeLabel, planDateLabel, shortlistCopyText
} from './planning.js';

const decimal = new Intl.NumberFormat('en', { maximumFractionDigits: 3 });
const percent = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 1 });
const checkedTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Madrid', dateStyle: 'medium', timeStyle: 'short'
});

function explanation(evaluation) {
  if (evaluation.status === 'uncertain') return 'The event type is unclear from this listing. It remains eligible for the usual ranking.';
  if (evaluation.status === 'fallback') return 'The event-type check is unavailable. This event remains eligible for the usual ranking.';
  return evaluation.decision === 'irrelevant'
    ? 'This listing did not match your selected event types.'
    : 'This event passed the event-type check. Your other saved preferences still guide ranking.';
}

function EvaluationDetails({ evaluation }) {
  const { components, status, irrelevance_score: score, threshold, model } = evaluation;
  return (
    <details className="evaluation-details">
      <summary>Why this result?</summary>
      <p>{explanation(evaluation)}</p>
      {status === 'evaluated' ? (
        <p className="evaluation-score">Irrelevance score: <strong>{decimal.format(score)} of 1</strong>. Limit: {decimal.format(threshold)}.</p>
      ) : <p className="evaluation-score">No irrelevance score is available.</p>}
      {model ? <p>Event-type model: {model}</p> : null}
      {components.length ? (
        <>
          <p>Each selected type is an alternative. A clear match to one can keep an event eligible. Only scores above the limit are marked irrelevant. This check alone does not establish suitability or a final recommendation.</p>
          <p>Match chance estimates the event type. Confidence describes certainty about either answer, including a “no”.</p>
          <ul className="evaluation-components">
            {components.map((component) => (
              <li key={component.question_id}>
                <h5>{eventTypeLabel(component.event_type)}</h5>
                <dl>
                  <div><dt>Match chance</dt><dd>{percent.format(component.p_yes)}</dd></div>
                  <div><dt>Confidence in the answer</dt><dd>{percent.format(component.confidence)}</dd></div>
                  <div><dt>Share of the score</dt><dd>{percent.format(component.weight)}</dd></div>
                  <div><dt>Added to irrelevance score</dt><dd>{component.contribution === null ? 'Not scored' : decimal.format(component.contribution)}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </details>
  );
}

function EvaluationCard({ evaluation }) {
  const { event, decision } = evaluation;
  return (
    <article className={'evaluation-card evaluation-' + decision}>
      <p className="evaluation-decision">
        {decision === 'eligible' ? 'Eligible for your digest' : decision === 'irrelevant' ? 'Irrelevant for your selected types' : 'Match not determined'}
      </p>
      <h4><a href={event.url} target="_blank" rel="noopener noreferrer">{event.title}<span className="sr-only"> (opens in a new tab)</span></a></h4>
      <p>{explanation(evaluation)}</p>
      <EvaluationDetails evaluation={evaluation} />
    </article>
  );
}

async function copyText(value) {
  if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
  await navigator.clipboard.writeText(value);
}

function downloadCalendar(event, reminder) {
  const content = eventCalendar(event, { reminder });
  const url = URL.createObjectURL(new Blob([content], { type: 'text/calendar;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = calendarFilename(event);
  document.body.append(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function ActionStatus({ status }) {
  return status ? <p className="plan-status" role={status.error ? 'alert' : 'status'}>{status.message}</p> : null;
}

function PlanCard({ event, evaluation, onSaveEvent, disabled }) {
  const [reminder, setReminder] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  const directions = directionsUrl(event.location);
  const act = async (action, message, error) => {
    setBusy(true);
    setStatus(null);
    try {
      await action();
      setStatus({ message });
    } catch {
      setStatus({ message: error, error: true });
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="plan-card" aria-labelledby={'plan-' + event.id}>
      <h4 id={'plan-' + event.id}>{event.title}</h4>
      <p className="plan-time">{eventTimeLabel(event)}</p>
      <dl className="plan-facts">
        <div><dt>Source</dt><dd>{event.source.replace(/_/g, ' ')}</dd></div>
        {event.location.trim() ? <div><dt>Location</dt><dd>{event.location}</dd></div> : null}
      </dl>
      {event.description.trim() ? <p className="plan-description">{event.description.length > 320 ? event.description.slice(0, 320) + '…' : event.description}</p> : null}
      <p className="plan-reason">{event.reason}</p>
      {event.used_fallback ? <p className="subscription-note">Personalized ordering was unavailable, so these plans use the usual fallback order.</p> : null}
      <div className="plan-actions">
        <a href={event.url} target="_blank" rel="noopener noreferrer">View organizer details<span className="sr-only"> for {event.title} (opens in a new tab)</span></a>
        {directions ? <a href={directions} target="_blank" rel="noopener noreferrer">Directions<span className="sr-only"> to {event.location} (opens Google Maps in a new tab)</span></a> : null}
        {onSaveEvent ? <button type="button" disabled={disabled || busy} onClick={() => act(() => onSaveEvent(event.id), 'Plan saved to your account.', 'We could not save this plan. Please try again.')}>Save plan<span className="sr-only">: {event.title}</span></button> : null}
        <button type="button" disabled={disabled || busy} onClick={() => act(() => copyText(eventCopyText(event)), 'Public event details copied.', 'We could not copy this event. You can open its organizer link instead.')}>Copy event<span className="sr-only">: {event.title}</span></button>
        {canExportCalendar(event) ? <button type="button" disabled={disabled || busy} onClick={() => act(() => downloadCalendar(event, reminder), 'Calendar file prepared. Open it to save the event.', 'We could not prepare the calendar file. Please try again.')}>{event.time_precision === 'date' ? 'Save date to calendar' : 'Add to calendar'}<span className="sr-only">: {event.title}</span></button> : null}
      </div>
      {event.time_precision === 'datetime' ? (
        <label className="plan-reminder"><input type="checkbox" checked={reminder} disabled={disabled || busy} onChange={(change) => setReminder(change.target.checked)} /> Include a one-hour reminder in this calendar file<span className="sr-only"> for {event.title}</span></label>
      ) : <p className="subscription-note">{event.time_precision === 'date' ? 'Saving the date does not confirm a start time. Check the organizer details.' : 'Confirm the date with the organizer before adding this event to your calendar.'}</p>}
      <ActionStatus status={status} />
      {evaluation ? <EvaluationDetails evaluation={evaluation} /> : null}
    </article>
  );
}

function resultState(plans) {
  if (plans.coverage.state !== 'complete') return plans.coverage.state;
  if (plans.recommendations.length) return 'recommendations';
  return plans.coverage.collected_count > 0 && plans.excluded_count === plans.coverage.collected_count ? 'filtered' : 'empty';
}

function resultMessage(plans) {
  const date = planDateLabel(plans.date);
  if (plans.coverage.state === 'unavailable') return 'We could not check the event sources for ' + date + '. This search is incomplete; please try again.';
  if (plans.coverage.state === 'partial') return 'Some sources could not be checked. Results for ' + date + ' may be incomplete.';
  if (!plans.coverage.collected_count) return "We haven't found any listings for " + date + ' in the sources checked so far.';
  if (resultState(plans) === 'filtered') return 'We checked ' + plans.coverage.collected_count + ' listing' + (plans.coverage.collected_count === 1 ? '' : 's') + ' for ' + date + '. None matched your selected event types.';
  if (!plans.recommendations.length) return 'No recommendations for ' + date + ' from the checked listings.';
  return plans.recommendations.length + ' plan' + (plans.recommendations.length === 1 ? '' : 's') + ' selected for ' + date + '.';
}

function VoluntaryFeedback({ plans, onFeedback, disabled }) {
  const [action, setAction] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(null);
  const submit = async (useful) => {
    setBusy(true);
    setStatus(null);
    try {
      await onFeedback({ date: plans.date, result_state: resultState(plans), useful, action: action || null });
      setStatus({ message: 'Thank you. Your feedback was saved.' });
    } catch {
      setStatus({ message: 'We could not save your feedback. Please try again.', error: true });
    } finally {
      setBusy(false);
    }
  };
  return (
    <fieldset className="preview-feedback" disabled={disabled || busy}>
      <legend>Was this useful for planning?</legend>
      <p>Optional feedback for the study you joined. Opening links does not submit feedback.</p>
      <label>Action I chose (optional)
        <select value={action} onChange={(event) => setAction(event.target.value)}>
          <option value="">No action to report</option>
          <option value="organizer">Viewed organizer details</option>
          <option value="save">Saved a plan</option>
          <option value="copy">Copied an event or shortlist</option>
          <option value="calendar">Prepared a calendar file</option>
        </select>
      </label>
      <div className="preview-actions">
        <button type="button" onClick={() => submit(true)}>Useful</button>
        <button type="button" onClick={() => submit(false)}>Not useful</button>
      </div>
      <ActionStatus status={status} />
    </fieldset>
  );
}

function Plans({ plans, evaluations, onRetry, onEditPreferences, onSaveEvent, onFeedback, disabled }) {
  const [copyStatus, setCopyStatus] = useState(null);
  const [copying, setCopying] = useState(false);
  const recommended = new Set(plans.recommendations.map((event) => event.event_key));
  const otherEvaluations = (evaluations || []).filter((item) => !recommended.has(item.event.event_key));
  const byKey = new Map((evaluations || []).map((item) => [item.event.event_key, item]));
  const copy = async () => {
    setCopying(true);
    setCopyStatus(null);
    try {
      await copyText(shortlistCopyText(plans.recommendations));
      setCopyStatus({ message: 'Public shortlist copied. Your preferences and ranking details are not included.' });
    } catch {
      setCopyStatus({ message: 'We could not copy the shortlist. You can open the organizer links instead.', error: true });
    } finally {
      setCopying(false);
    }
  };
  return (
    <>
      <p className="preview-result-message" role="status">{resultMessage(plans)}</p>
      <p className="preview-checked">Last checked <time dateTime={plans.checked_at}>{checkedTime.format(new Date(plans.checked_at))}</time> (València time).</p>
      {plans.coverage.state === 'partial' && !plans.recommendations.length ? <p>No recommendations from the sources checked so far.</p> : null}
      <div className="preview-actions">
        {onRetry ? <button type="button" disabled={disabled} onClick={onRetry}>Check again</button> : null}
        {onEditPreferences ? <button type="button" disabled={disabled} onClick={onEditPreferences}>Edit my choices</button> : null}
        {plans.recommendations.length ? <button type="button" disabled={disabled || copying} onClick={copy}>Copy shortlist</button> : null}
      </div>
      <ActionStatus status={copyStatus} />
      <div className="plan-list">
        {plans.recommendations.map((event) => <PlanCard key={event.id} event={event} evaluation={byKey.get(event.event_key)} onSaveEvent={onSaveEvent} disabled={disabled} />)}
      </div>
      {otherEvaluations.length ? (
        <details className="preview-other-events">
          <summary>Other checked listings ({otherEvaluations.length})</summary>
          <p>These listings are outside this ranked shortlist. Their checks remain available for review.</p>
          <div className="evaluation-list">{otherEvaluations.map((evaluation) => <EvaluationCard key={evaluation.event.event_key} evaluation={evaluation} />)}</div>
        </details>
      ) : null}
      <details className="preview-coverage">
        <summary>Sources checked ({plans.coverage.sources.length})</summary>
        {plans.coverage.sources.length ? <ul>{plans.coverage.sources.map((source) => <li key={source.name}>{source.name.replace(/_/g, ' ')}: {source.status === 'ok' ? 'checked, ' + source.event_count + ' listings for this date' : 'could not be checked'} · <time dateTime={source.checked_at}>{checkedTime.format(new Date(source.checked_at))}</time></li>)}</ul> : <p>No source checks were available.</p>}
      </details>
      {onFeedback ? <VoluntaryFeedback plans={plans} onFeedback={onFeedback} disabled={disabled} /> : null}
    </>
  );
}

export default function DigestPreview({ state, onRetry, disabled, onEditPreferences, onSaveEvent, onFeedback }) {
  const headingRef = useRef(null);
  const errorRef = useRef(null);
  useEffect(() => {
    if (state.status === 'ready') headingRef.current?.focus();
    if (state.status === 'error') errorRef.current?.focus();
  }, [state]);

  if (state.status === 'idle') return null;
  if (state.status === 'loading') return <p className="status-message" role="status">Finding plans from your saved profile… No email will be sent.</p>;
  if (state.status === 'error') {
    return (
      <div className="digest-preview preview-error">
        <p className="error-message" role="alert" tabIndex="-1" ref={errorRef}>{state.message}</p>
        {state.retryable !== false ? <button className="back-button" disabled={disabled} onClick={onRetry} type="button">Retry preview</button> : null}
        {onEditPreferences ? <button className="back-button" disabled={disabled} onClick={onEditPreferences} type="button">Edit my choices</button> : null}
      </div>
    );
  }

  const { summary, evaluations, selectedTypes, plans } = state.result;
  const allIrrelevant = evaluations?.length > 0 && evaluations.every((item) => item.decision === 'irrelevant');
  return (
    <section className="digest-preview" aria-labelledby="preview-title">
      <h3 id="preview-title" tabIndex="-1" ref={headingRef}>{plans ? 'Plans for ' + planDateLabel(plans.date) : 'Tomorrow’s preview'}</h3>
      <p>Using your saved event types:</p>
      <ul className="preview-selected-types" aria-label="Saved event types used for this preview">{selectedTypes.map((type) => <li key={type}>{eventTypeLabel(type)}</li>)}</ul>
      {plans ? (
        <Plans key={plans.checked_at + ':' + plans.date + ':' + summary.correlation_id} plans={plans} evaluations={evaluations} onRetry={onRetry} onEditPreferences={onEditPreferences} onSaveEvent={onSaveEvent} onFeedback={onFeedback} disabled={disabled} />
      ) : (
        <>
          <p className="preview-result-message" role="status">{!summary.event_count ? 'No events found for tomorrow in this older preview. Try again later.' : allIrrelevant ? 'All evaluated events are irrelevant for your selected types.' : summary.event_count + ' event' + (summary.event_count === 1 ? '' : 's') + ' found for tomorrow.'}</p>
          <p>The ranked shortlist is not available in this older preview.</p>
          {evaluations === null ? <p>Event-type explanations are not available yet. This preview uses the existing ranking.</p> : null}
          {summary.event_count > 0 && evaluations?.length === 0 ? <p>No event-type evaluations are available for this preview.</p> : null}
          {evaluations?.length ? <details className="preview-other-events"><summary>Event-type checks ({evaluations.length})</summary><div className="evaluation-list">{evaluations.map((evaluation) => <EvaluationCard key={evaluation.event.event_key} evaluation={evaluation} />)}</div></details> : null}
        </>
      )}
      <p className="subscription-note">No email was sent.</p>
      <details className="preview-support">
        <summary>Preview details</summary>
        <p>Preview reference: {summary.correlation_id}. Rendered {summary.rendered_count} private preview{summary.rendered_count === 1 ? '' : 's'}.</p>
      </details>
    </section>
  );
}
