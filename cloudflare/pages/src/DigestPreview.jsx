import { useEffect, useRef } from 'react';

import { eventTypeLabel } from './preview.js';

const decimal = new Intl.NumberFormat('en', { maximumFractionDigits: 3 });
const percent = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 1 });

function explanation(evaluation) {
  if (evaluation.status === 'uncertain') {
    return 'The answers are too uncertain to score. This event remains eligible for the usual ranking.';
  }
  if (evaluation.status === 'fallback') {
    const messages = {
      feature_disabled: 'Event-type checks are switched off for this preview.',
      invalid_preferences: 'Your saved event types need review. Edit and save your profile.',
      budget_exhausted: 'There was not enough time to check this event.'
    };
    return `${messages[evaluation.error_code] || 'The event-type check is temporarily unavailable.'} This event remains eligible for the usual ranking.`;
  }
  return evaluation.decision === 'irrelevant'
    ? 'Its irrelevance score is above the limit for your selected event types.'
    : 'This event passed the event-type check. Your other saved preferences still guide ranking.';
}

function EvaluationCard({ evaluation }) {
  const { event, components, decision, status, irrelevance_score: score, threshold } = evaluation;
  return (
    <article className={`evaluation-card evaluation-${decision}`}>
      <p className="evaluation-decision">
        {decision === 'eligible' ? 'Eligible for your digest' : decision === 'irrelevant' ? 'Irrelevant for your selected types' : 'Match not determined'}
      </p>
      <h4><a href={event.url} target="_blank" rel="noopener noreferrer">{event.title}<span className="sr-only"> (opens in a new tab)</span></a></h4>
      <p>{explanation(evaluation)}</p>
      {status === 'evaluated' ? (
        <p className="evaluation-score">Irrelevance score: <strong>{decimal.format(score)} of 1</strong>. Limit: {decimal.format(threshold)}.</p>
      ) : <p className="evaluation-score">No irrelevance score is available.</p>}
      {components.length ? (
        <details className="evaluation-details">
          <summary>Why this result?</summary>
          <p>Each selected type is an alternative. A clear match to one can keep an event eligible. Higher irrelevance scores mean less relevant; only scores above the limit are marked irrelevant.</p>
          <p>Match chance estimates whether an event is this type. Confidence measures how sure Jev is about either answer, including a “no”. Each type has an equal share of the score.</p>
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
        </details>
      ) : null}
    </article>
  );
}

export default function DigestPreview({ state, onRetry, disabled }) {
  const headingRef = useRef(null);
  const errorRef = useRef(null);
  useEffect(() => {
    if (state.status === 'ready') headingRef.current?.focus();
    if (state.status === 'error') errorRef.current?.focus();
  }, [state]);

  if (state.status === 'idle') return null;
  if (state.status === 'loading') {
    return <p className="status-message" role="status">Preparing tomorrow’s preview from your saved profile… No email will be sent.</p>;
  }
  if (state.status === 'error') {
    return (
      <div className="digest-preview preview-error">
        <p className="error-message" role="alert" tabIndex="-1" ref={errorRef}>{state.message}</p>
        {state.retryable !== false ? <button className="back-button" disabled={disabled} onClick={onRetry} type="button">Retry preview</button> : null}
      </div>
    );
  }

  const { summary, evaluations, selectedTypes } = state.result;
  const allIrrelevant = evaluations?.length > 0 && evaluations.every((item) => item.decision === 'irrelevant');
  return (
    <section className="digest-preview" aria-labelledby="preview-title">
      <h3 id="preview-title" tabIndex="-1" ref={headingRef}>Tomorrow’s preview</h3>
      <p>Using your saved event types:</p>
      <ul className="preview-selected-types" aria-label="Saved event types used for this preview">
        {selectedTypes.map((type) => <li key={type}>{eventTypeLabel(type)}</li>)}
      </ul>
      {!summary.event_count ? (
        <p className="status-message" role="status">No events found for tomorrow. Try again later.</p>
      ) : (
        <p className="preview-result-message" role="status">
          {allIrrelevant
            ? 'All evaluated events are irrelevant for your selected types.'
            : `${summary.event_count} event${summary.event_count === 1 ? '' : 's'} found for tomorrow.`}
        </p>
      )}
      {evaluations === null ? <p>Event-type explanations are not available yet. This preview uses the existing ranking.</p> : null}
      {summary.event_count > 0 && evaluations?.length === 0 ? <p>No event-type evaluations are available for this preview.</p> : null}
      <div className="evaluation-list">
        {evaluations?.map((evaluation) => <EvaluationCard key={evaluation.event.event_key} evaluation={evaluation} />)}
      </div>
      <p className="subscription-note">No email was sent. Preview reference: {summary.correlation_id}. Rendered {summary.rendered_count} private preview{summary.rendered_count === 1 ? '' : 's'}.</p>
    </section>
  );
}
