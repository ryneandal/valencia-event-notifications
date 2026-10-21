import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  apiFetch,
  loadCurrentUser,
  logoutUser,
  registerUser,
  resumeUser,
  runDigestPreview,
  updateSubscription,
  updateUserProfile,
  verifyMagicLink
} from './api.js';
import {
  AUDIENCE_OPTIONS,
  DEFAULT_FORM_STATE,
  INTEREST_CLUSTERS,
  LOCATION_OPTIONS,
  NEGATIVE_SIGNAL_OPTIONS,
  POSITIVE_SIGNAL_OPTIONS,
  SEASONAL_ANCHORS,
  buildPersonalizationProfile,
  hydrateFormState
} from './profile.js';
import { onboardingStepFor, validateEmail, validateOnboardingStep, validationTargetId } from './onboarding.js';
import DigestPreview from './DigestPreview.jsx';
import PlanningTools from './PlanningTools.jsx';
import { parseDigestPreview, savedEventTypes } from './preview.js';

const STEPS = [
  { eyebrow: 'Your people & place', title: 'Who are we planning for?', intro: 'Choose your audience. We currently check a small set of València city sources, so coverage varies by day and event type.' },
  { eyebrow: 'Your spark', title: 'Which events interest you?', intro: 'Choose one or more event types. You can change your choices later.' },
  { eyebrow: 'Optional refinements', title: 'Anything else that matters?', intro: 'These choices guide ranking, but do not guarantee suitability or accessibility. You can skip them or change them later.' },
  { eyebrow: 'Account & review', title: 'Save your choices.', intro: 'Review your preferences, then confirm your email to see plans based on your saved choices.' }
];

function localDate() {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const part = (type) => parts.find((item) => item.type === type).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function dateLabel(date) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Madrid', weekday: 'long', day: 'numeric', month: 'long'
  }).format(new Date(`${date}T12:00:00Z`));
}

function isDateOnly(date) {
  if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  const parsed = new Date(`${date}T12:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date;
}

function availablePlanningDates(data) {
  if (!Array.isArray(data?.available_dates)) return [];
  return [...new Set(data.available_dates)].filter(isDateOnly).sort().slice(0, 7);
}

function toggleValue(values, value) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function ChoiceCard({ checked, detail, label, name, onChange, value }) {
  return (
    <label className="choice-card">
      <input
        checked={checked}
        name={name}
        onChange={() => onChange(value)}
        type="radio"
        value={value}
      />
      <span className="choice-icon" aria-hidden="true">●</span>
      <strong>{label}</strong>
      <small>{detail}</small>
    </label>
  );
}

function ToggleChip({ checked, icon, label, onChange }) {
  return (
    <label className={`interest-chip ${checked ? 'is-checked' : ''}`}>
      <input checked={checked} onChange={onChange} type="checkbox" />
      {icon ? <span className="interest-symbol" aria-hidden="true">{icon}</span> : null}
      <span>{label}</span>
      <b aria-hidden="true">✓</b>
    </label>
  );
}

function StoryPanel() {
  return (
    <section className="story-panel" aria-label="About Brisa">
      <a className="brand" href="#onboarding" aria-label="Brisa onboarding home">
        <span className="brand-mark" aria-hidden="true">
          <img src="/brand/brisa-mark.png" alt="" width="37" height="37" />
        </span>
        <span>BRISA</span>
      </a>
      <div className="story-copy">
        <p className="eyebrow">VALÈNCIA, TOMORROW</p>
        <h1>Make room for <em>something lovely.</em></h1>
        <p>
          Find something to do in València, shaped around your people and your
          pace. Save your choices and explore the listings we find.
        </p>
      </div>
      <div className="sunset-illustration" aria-hidden="true">
        <div className="sun" />
        <div className="building building-one" />
        <div className="building building-two" />
        <div className="building building-three" />
        <div className="palm" />
        <div className="sea-line sea-one" />
        <div className="sea-line sea-two" />
      </div>
      <div className="story-footer">
        <div><strong>Tomorrow, considered.</strong><span>Made beside the Mediterranean</span></div>
      </div>
    </section>
  );
}

function ReviewList({ form, onEdit }) {
  const audience = AUDIENCE_OPTIONS.find(({ value }) => value === form.audience)?.label;
  const locations = LOCATION_OPTIONS.filter(({ value }) => form.locations.includes(value)).map(({ label }) => label);
  const interests = INTEREST_CLUSTERS.filter(({ name }) => form.interests.includes(name)).map(({ label }) => label);
  const anchors = SEASONAL_ANCHORS.filter(({ name }) => form.seasonalAnchors.includes(name)).map(({ label }) => label);
  const positives = POSITIVE_SIGNAL_OPTIONS.filter(([value]) => form.positiveSignals.includes(value)).map(([, label]) => label);
  const negatives = NEGATIVE_SIGNAL_OPTIONS.filter(([value]) => form.negativeSignals.includes(value)).map(([, label]) => label);

  return (
    <div className="review-card">
      {[
        ['Planning for', audience || 'Choose an audience', 0, 'audience'],
        ['Area preferences', locations.join(', ') || 'Choose an area', 0, 'areas'],
        ['Event types', interests.join(', ') || 'Choose event types', 1, 'event types'],
        ['Show me more', positives.join(', ') || 'No extra preferences', 2, 'priorities'],
        ['Usually avoid', negatives.join(', ') || 'No extra preferences', 2, 'things to avoid'],
        ['Seasonal interests', anchors.join(', ') || 'None selected', 2, 'seasonal interests']
      ].map(([label, value, step, editLabel]) => (
        <div className="review-row" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <button className="text-button review-edit" type="button" onClick={() => onEdit(step)} aria-label={`Edit ${editLabel}`}>Edit</button>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const initialized = useRef(false);
  const stepTitleRef = useRef(null);
  const completionTitleRef = useRef(null);
  const requestErrorRef = useRef(null);
  const previewRequest = useRef(0);
  const previewController = useRef(null);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(DEFAULT_FORM_STATE);
  const [currentUser, setCurrentUser] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [existingAccountEmail, setExistingAccountEmail] = useState(null);
  const [validationError, setValidationError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [completion, setCompletion] = useState(null);
  const [preview, setPreview] = useState({ status: 'idle' });
  const [sessionExpired, setSessionExpired] = useState(false);
  const [signInOnly, setSignInOnly] = useState(false);
  const [returnToReview, setReturnToReview] = useState(false);
  const [planning, setPlanning] = useState(null);
  const [planningStatus, setPlanningStatus] = useState('loading');
  const [planningRefreshKey, setPlanningRefreshKey] = useState(0);
  const [selectedDate, setSelectedDate] = useState('');

  const profile = useMemo(() => buildPersonalizationProfile(form), [form]);
  const savedLocations = useMemo(() => currentUser
    ? hydrateFormState(currentUser.email, currentUser.preferences_blob).locations
    : [], [currentUser?.email, currentUser?.preferences_blob]);
  const current = STEPS[step];
  const availableDates = useMemo(() => availablePlanningDates(planning), [planning]);
  const accountIdentity = currentUser ? `${currentUser.id || ''}:${currentUser.email}` : '';

  const clearPreview = useCallback(() => {
    previewRequest.current += 1;
    previewController.current?.abort();
    previewController.current = null;
    setPreview({ status: 'idle' });
  }, []);

  const handlePlanningChange = useCallback((data) => {
    const usable = data?.version === 'brisa-planning-v1' && typeof data.delivery_enabled === 'boolean' ? data : null;
    const dates = availablePlanningDates(usable);
    setPlanning(usable);
    setPlanningStatus(usable ? 'ready' : 'unavailable');
    setSelectedDate((previous) => dates.includes(previous) ? previous : dates[0] || '');
  }, []);

  const handlePlanningUserChange = useCallback((user) => {
    setCurrentUser(user);
    setForm(hydrateFormState(user.email, user.preferences_blob));
  }, []);

  useEffect(() => {
    setPlanning(null);
    setPlanningStatus('loading');
    setSelectedDate('');
  }, [accountIdentity]);

  useEffect(() => {
    clearPreview();
  }, [accountIdentity, currentUser?.preferences_blob, selectedDate, clearPreview]);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    const url = new URL(window.location.href);
    if (url.pathname === '/auth/verify') {
      const token = url.searchParams.get('token');
      if (!token) {
        setSignInOnly(true);
        setStep(3);
        setError('This sign-in link is missing its token. Request a new link.');
        return;
      }
      setBusy(true);
      verifyMagicLink(token)
        .then(({ user }) => {
          setCurrentUser(user);
          setForm(hydrateFormState(user.email, user.preferences_blob));
          setCompletion({ kind: 'verified', email: user.email });
          window.history.replaceState({}, '', '/');
        })
        .catch((requestError) => {
          setSignInOnly(true);
          setStep(3);
          setError(requestError.message);
        })
        .finally(() => setBusy(false));
      return;
    }

    loadCurrentUser()
      .then(({ user }) => {
        setCurrentUser(user);
        setForm(hydrateFormState(user.email, user.preferences_blob));
        setCompletion({ kind: 'account', email: user.email });
      })
      .catch((requestError) => {
        if (![401, 404].includes(requestError.status)) {
          setError('We could not check your saved session.');
        }
      });
  }, []);

  useEffect(() => {
    if (!completion) stepTitleRef.current?.focus();
  }, [step, signInOnly, completion]);

  useEffect(() => {
    if (!validationError) return;
    document.getElementById(validationTargetId(validationError.field))?.focus();
  }, [validationError]);

  useEffect(() => {
    if (sessionExpired) document.getElementById('email')?.focus();
  }, [sessionExpired]);

  useEffect(() => {
    if (completion) completionTitleRef.current?.focus();
  }, [completion]);

  useEffect(() => {
    if (error) requestErrorRef.current?.focus();
  }, [error]);

  useEffect(() => () => {
    previewRequest.current += 1;
    previewController.current?.abort();
  }, []);

  const expireSession = () => {
    clearPreview();
    setCurrentUser(null);
    setForm({ ...DEFAULT_FORM_STATE, email: currentUser?.email || form.email });
    setCompletion(null);
    setStep(3);
    setSignInOnly(true);
    setNotice('Your session has expired. Enter your email and request a sign-in link to return to your plans.');
    setError('');
    setSessionExpired(true);
  };

  const editProfile = () => {
    clearPreview();
    setError('');
    setNotice('');
    setValidationError(null);
    setSignInOnly(false);
    setReturnToReview(false);
    setForm(hydrateFormState(currentUser?.email, currentUser?.preferences_blob));
    setCompletion(null);
    setStep(3);
  };

  const editReviewSection = (nextStep) => {
    setError('');
    setValidationError(null);
    setReturnToReview(true);
    setStep(nextStep);
  };

  const clearValidationError = (field) => {
    setValidationError((currentError) =>
      currentError?.field === field ? null : currentError
    );
  };

  const updateList = (field, value) => {
    setForm((previous) => ({ ...previous, [field]: toggleValue(previous[field], value) }));
    clearValidationError(field);
  };

  const goNext = async () => {
    if (busy) return;
    setError('');
    setExistingAccountEmail(null);
    const nextValidationError = validateOnboardingStep(step, form);
    if (nextValidationError) {
      setStep(onboardingStepFor(nextValidationError.field));
      setValidationError(nextValidationError);
      return;
    }
    setValidationError(null);
    if (step < STEPS.length - 1) {
      setStep((value) => returnToReview ? STEPS.length - 1 : value + 1);
      setReturnToReview(false);
      return;
    }

    clearPreview();
    setBusy(true);
    try {
      const payload = currentUser
        ? await updateUserProfile(profile)
        : await registerUser(form.email.trim(), profile);
      if (currentUser) {
        setCurrentUser(payload.user);
        setForm(hydrateFormState(payload.user.email, payload.user.preferences_blob));
        setCompletion({ kind: 'saved', email: payload.user.email });
        setNotice('Your personalisation profile is saved.');
      } else {
        setCompletion({ kind: 'link-sent', email: form.email.trim() });
        setNotice('Check your inbox to confirm your address and open your plans.');
      }
    } catch (requestError) {
      if (requestError.status === 401) expireSession();
      else if (requestError.status === 409) {
        setExistingAccountEmail(form.email.trim());
        setError('This email already has an account. Send a sign-in link to continue.');
      } else if (requestError.field === 'interests') {
        setStep(1);
        setReturnToReview(true);
        setValidationError({ field: 'interests', message: requestError.message });
      } else setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const resume = async () => {
    if (busy) return;
    setError('');
    const emailValidationError = validateEmail(form.email);
    if (emailValidationError) {
      setValidationError(emailValidationError);
      return;
    }
    setValidationError(null);
    setBusy(true);
    try {
      await resumeUser(form.email.trim());
      setCompletion({ kind: 'link-sent', email: form.email.trim() });
      setNotice('Check your inbox for a secure sign-in link.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    clearPreview();
    setBusy(true);
    try {
      await logoutUser();
      setCurrentUser(null);
      setForm(DEFAULT_FORM_STATE);
      setStep(0);
      setCompletion(null);
      setNotice('Signed out.');
      setSessionExpired(false);
      setSignInOnly(false);
      setValidationError(null);
      setExistingAccountEmail(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const changeSubscription = async (subscribed) => {
    clearPreview();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const { user } = await updateSubscription(subscribed);
      setCurrentUser(user);
      setCompletion({ kind: 'account', email: user.email });
      setPlanningRefreshKey((value) => value + 1);
      setNotice(
        subscribed
          ? 'Your email preference is saved. Delivery still depends on the service status below.'
          : 'Emails are paused. Your saved profile is still here whenever you return.'
      );
    } catch (requestError) {
      if (requestError.status === 401) expireSession();
      else setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const previewDigest = async () => {
    if (busy || !currentUser || completion?.kind === 'link-sent') return;
    clearPreview();
    const selectedTypes = savedEventTypes(currentUser.preferences_blob);
    if (!selectedTypes) {
      setPreview({ status: 'error', retryable: false, message: 'Your saved event types need review. Edit and save your profile before requesting a preview.' });
      return;
    }
    const requestId = previewRequest.current;
    const controller = new AbortController();
    previewController.current = controller;
    setError('');
    setNotice('');
    setPreview({ status: 'loading' });
    try {
      const payload = await runDigestPreview(fetch, { signal: controller.signal, date: selectedDate || undefined });
      if (requestId !== previewRequest.current) return;
      const result = parseDigestPreview(payload, selectedTypes);
      const responseDate = result.plans?.date || result.summary.digest_date;
      if (selectedDate && (responseDate ? responseDate !== selectedDate : selectedDate !== availableDates[0])) {
        throw new Error('This response does not confirm the selected day. Please try again.');
      }
      setPreview({ status: 'ready', result });
    } catch (requestError) {
      if (requestId !== previewRequest.current) return;
      if (requestError.status === 401) expireSession();
      else setPreview({ status: 'error', message: requestError.message });
    } finally {
      if (requestId === previewRequest.current) previewController.current = null;
    }
  };

  const saveEvent = async (eventId) => {
    try {
      const result = await apiFetch('/api/planning/saved', {
        method: 'POST', body: JSON.stringify({ event_id: eventId })
      });
      setPlanningRefreshKey((value) => value + 1);
      return result;
    } catch (requestError) {
      if (requestError.status === 401) expireSession();
      throw requestError;
    }
  };

  const sendFeedback = async ({ date, result_state, useful, action }) => {
    try {
      return await apiFetch('/api/planning/feedback', {
        method: 'POST', body: JSON.stringify({ date, result_state, useful, action })
      });
    } catch (requestError) {
      if (requestError.status === 401) expireSession();
      throw requestError;
    }
  };

  if (completion) {
    const awaitingVerification = completion.kind === 'link-sent';
    const justVerified = completion.kind === 'verified';
    const subscribed = currentUser?.is_subscribed !== false;
    const weekend = availableDates.find((date) => [0, 6].includes(new Date(`${date}T12:00:00Z`).getUTCDay()));
    const monday = availableDates.find((date) => new Date(`${date}T12:00:00Z`).getUTCDay() === 1);
    const tomorrowSelected = !selectedDate || selectedDate === availableDates[0];
    return (
      <main className="onboarding-shell" id="onboarding">
        <StoryPanel />
        <section className="form-panel success-screen account-planning">
          <div className="success-mark" aria-hidden="true">✦</div>
          <p className="eyebrow">
            {awaitingVerification
              ? 'CHECK YOUR INBOX'
              : justVerified ? 'EMAIL VERIFIED' : 'YOUR BRISA ACCOUNT'}
          </p>
          <h2 ref={completionTitleRef} tabIndex="-1">
            {awaitingVerification
              ? 'One quick step remains.'
              : 'Your València plans.'}
          </h2>
          <p>
            {awaitingVerification ? (
              <>We sent a secure, one-time link to <strong>{completion.email}</strong>. Open it to confirm your address and return to your plans.</>
            ) : (
              <>Find a shortlist using the saved choices for <strong>{completion.email}</strong>.</>
            )}
          </p>
          {notice ? <p className="status-message" role="status">{notice}</p> : null}
          {error ? <p className="error-message" role="alert" ref={requestErrorRef} tabIndex="-1">{error}</p> : null}
          {currentUser && !awaitingVerification ? (
            <div className="planning-date-controls">
              <p className="planning-local-date">Today in València: {dateLabel(isDateOnly(planning?.today) ? planning.today : localDate())}. Dates and times use Europe/Madrid.</p>
              {availableDates.length ? (
                <>
                  <label className="field-label" htmlFor="plan-date">Choose a day in the coming week</label>
                  <select className="text-input" id="plan-date" value={selectedDate} disabled={busy} onChange={(event) => {
                    if (!availableDates.includes(event.target.value)) return;
                    clearPreview();
                    setSelectedDate(event.target.value);
                  }}>
                    {availableDates.map((date) => <option key={date} value={date}>{dateLabel(date)}</option>)}
                  </select>
                  <div className="planning-date-shortcuts" aria-label="Date shortcuts">
                    {[
                      ['Tomorrow', availableDates[0]], ['This weekend', weekend], ['Next Monday', monday]
                    ].filter(([, date]) => date).map(([label, date]) => (
                      <button className="text-button" key={label} type="button" disabled={busy} onClick={() => {
                        clearPreview();
                        setSelectedDate(date);
                      }}>{label}</button>
                    ))}
                  </div>
                </>
              ) : <p>Tomorrow’s listings are available to check. More dates appear when account planning settings are available.</p>}
              <p className="planning-service-state" role="status">
                {planningStatus === 'loading'
                  ? 'Checking email delivery status…'
                  : !planning
                    ? 'Email delivery status is unavailable. You can still try tomorrow’s plans; checking plans sends no email.'
                    : !planning.delivery_enabled
                      ? 'Planning is available. Email delivery has not started yet.'
                      : subscribed
                        ? 'Email delivery is enabled for your selected delivery days.'
                        : 'Your email subscription is paused. Planning remains available.'}
              </p>
              {!subscribed && !planning?.delivery_enabled ? <p>Your email subscription preference is paused.</p> : null}
            </div>
          ) : null}
          <div className="success-actions">
            {awaitingVerification ? (
              <button className="next-button" onClick={() => { setCompletion(null); setStep(3); setNotice(''); }} type="button">Use another email</button>
            ) : null}
            {currentUser && !awaitingVerification ? (
              <button className="next-button" disabled={busy || preview.status === 'loading'} onClick={previewDigest} type="button">
                {preview.status === 'loading' ? 'Finding plans…' : tomorrowSelected ? 'See tomorrow’s plans' : `See plans for ${dateLabel(selectedDate)}`}
              </button>
            ) : null}
          </div>
          <DigestPreview
            state={preview}
            onRetry={previewDigest}
            disabled={busy}
            onEditPreferences={editProfile}
            onSaveEvent={saveEvent}
            onFeedback={planning?.pilot?.consented === true ? sendFeedback : undefined}
          />
          {currentUser && !awaitingVerification ? (
            <div className="account-secondary-actions">
              <button className="back-button" disabled={busy} onClick={editProfile} type="button">Edit my profile</button>
              <button className="text-button" disabled={busy} onClick={() => changeSubscription(!subscribed)} type="button">
                {subscribed ? 'Pause email digest' : 'Resume email digest'}
              </button>
              <button className="text-button" disabled={busy} onClick={signOut} type="button">Sign out</button>
            </div>
          ) : null}
          {currentUser && !awaitingVerification ? (
            <PlanningTools
              key={accountIdentity}
              user={currentUser}
              onUserChange={handlePlanningUserChange}
              onPlanningChange={handlePlanningChange}
              refreshKey={planningRefreshKey}
            />
          ) : null}
          {currentUser ? <p className="subscription-note">Pausing unsubscribes this address from delivery without deleting its saved profile or signing you out.</p> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="onboarding-shell" id="onboarding">
      <StoryPanel />
      <section className="form-panel">
        <header className="topbar">
          <span className="step-label">{signInOnly ? 'ACCOUNT ACCESS' : <>Step {String(step + 1).padStart(2, '0')} <span>of {String(STEPS.length).padStart(2, '0')}</span></>}</span>
          {currentUser ? (
            <button className="text-button" disabled={busy} onClick={() => {
              setForm(hydrateFormState(currentUser.email, currentUser.preferences_blob));
              setCompletion({ kind: 'account', email: currentUser.email });
              setError('');
              setValidationError(null);
            }} type="button">Back to plans</button>
          ) : !signInOnly ? (
            <button className="text-button" disabled={busy} onClick={() => {
              setSignInOnly(true);
              setStep(3);
              setError('');
              setValidationError(null);
            }} type="button">Already registered? Sign in</button>
          ) : null}
        </header>
        {!signInOnly ? <div
          className="progress-track"
          role="progressbar"
          aria-label="Onboarding progress"
          aria-valuemax={STEPS.length}
          aria-valuemin="1"
          aria-valuenow={step + 1}
          aria-valuetext={`Step ${step + 1} of ${STEPS.length}: ${current.eyebrow}`}
        >
          <div className="progress-bar" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
        </div> : null}

        <form className="form-inner" noValidate onSubmit={(event) => { event.preventDefault(); void (signInOnly ? resume() : goNext()); }} aria-busy={busy}>
          <section className="step is-current" aria-labelledby="step-title">
            <p className="eyebrow">{signInOnly ? 'Welcome back' : current.eyebrow}</p>
            <h2 id="step-title" ref={stepTitleRef} tabIndex="-1">{signInOnly ? 'Return to your plans.' : current.title}</h2>
            <p className="step-intro">{signInOnly ? 'Request a secure sign-in link. Your saved choices will be waiting for you.' : currentUser && step === 3 ? 'Review and save changes explicitly. Plans always use your saved profile.' : current.intro}</p>

            {step === 0 ? (
              <>
                <fieldset
                  className="choice-grid"
                  id="audience-fieldset"
                  aria-describedby={validationError?.field === 'audience' ? 'audience-error' : undefined}
                  aria-invalid={validationError?.field === 'audience'}
                  aria-required="true"
                  tabIndex="-1"
                >
                  <legend className="sr-only">Choose who the plans are for</legend>
                  {AUDIENCE_OPTIONS.map((option) => (
                    <ChoiceCard key={option.value} {...option} checked={form.audience === option.value} name="audience" onChange={(audience) => {
                      setForm((previous) => ({ ...previous, audience }));
                      clearValidationError('audience');
                    }} />
                  ))}
                </fieldset>
                {validationError?.field === 'audience' ? <p className="field-error" id="audience-error" role="alert">{validationError.message}</p> : null}
                <p id="coverage-hint" className="coverage-note">Current coverage focuses on València city. We do not yet promise a complete city agenda, metro-area search, or day-trip listings.</p>
                <fieldset
                  className="choice-grid location-grid"
                  id="locations-fieldset"
                  aria-describedby={`coverage-hint${validationError?.field === 'locations' ? ' locations-error' : ''}`}
                  aria-invalid={validationError?.field === 'locations'}
                  aria-required="true"
                  tabIndex="-1"
                >
                  <legend className="sr-only">Area preferences</legend>
                  {LOCATION_OPTIONS.filter(({ value, available }) => available || savedLocations.includes(value)).map(({ value, label, detail }) => (
                    <ToggleChip key={value} checked={form.locations.includes(value)} icon="⌖" label={<><strong>{label}</strong><small>{detail}</small></>} onChange={() => updateList('locations', value)} />
                  ))}
                </fieldset>
                {validationError?.field === 'locations' ? <p className="field-error" id="locations-error" role="alert">{validationError.message}</p> : null}
              </>
            ) : null}

            {step === 1 ? (
              <>
                <fieldset
                  className="interest-grid"
                  id="interests-fieldset"
                  aria-describedby={`interests-hint${validationError?.field === 'interests' ? ' interests-error' : ''}`}
                  aria-invalid={validationError?.field === 'interests'}
                  aria-required="true"
                  tabIndex="-1"
                >
                  <legend className="sr-only">Choose event types</legend>
                  {INTEREST_CLUSTERS.map(({ name, label, icon, includes }) => (
                    <ToggleChip key={name} checked={form.interests.includes(name)} icon={icon} label={<><strong>{label}</strong><small>{includes.slice(0, 3).join(' · ')}</small></>} onChange={() => updateList('interests', name)} />
                  ))}
                </fieldset>
                <p id="interests-hint" role="status">{form.interests.length} of {INTEREST_CLUSTERS.length} event types selected. Choose any that interest you.</p>
                {validationError?.field === 'interests' ? <p className="field-error" id="interests-error" role="alert">{validationError.message}</p> : null}
              </>
            ) : null}

            {step === 2 ? (
              <>
                <button className="text-button skip-refinements" type="button" onClick={() => { setStep(3); setReturnToReview(false); }}>Skip optional refinements</button>
                <div className="signals-layout">
                <fieldset className="signal-group">
                  <legend>Show me more</legend>
                  <div className="signal-grid">
                    {POSITIVE_SIGNAL_OPTIONS.map(([value, label]) => <ToggleChip key={value} checked={form.positiveSignals.includes(value)} label={label} onChange={() => updateList('positiveSignals', value)} />)}
                  </div>
                </fieldset>
                <fieldset className="signal-group avoid-group">
                  <legend>Usually avoid</legend>
                  <div className="signal-grid">
                    {NEGATIVE_SIGNAL_OPTIONS.map(([value, label]) => <ToggleChip key={value} checked={form.negativeSignals.includes(value)} label={label} onChange={() => updateList('negativeSignals', value)} />)}
                  </div>
                </fieldset>
                </div>
                <fieldset className="season-grid">
                  <legend>Seasonal interests (optional)</legend>
                  {SEASONAL_ANCHORS.map(({ name, label, months, notes }) => (
                    <ToggleChip key={name} checked={form.seasonalAnchors.includes(name)} icon="☼" label={<><strong>{label}</strong><small>{months.join(' / ')} · {notes}</small></>} onChange={() => updateList('seasonalAnchors', name)} />
                  ))}
                </fieldset>
              </>
            ) : null}

            {step === 3 ? (
              <>
                <label className="field-label" htmlFor="email">{currentUser ? 'Account email' : 'Email address'}</label>
                <input
                  autoComplete="email"
                  className="text-input"
                  id="email"
                  aria-describedby={`email-hint${validationError?.field === 'email' ? ' email-error' : ''}`}
                  aria-invalid={validationError?.field === 'email'}
                  onChange={(event) => {
                    setForm((previous) => ({ ...previous, email: event.target.value }));
                    clearValidationError('email');
                    setExistingAccountEmail(null);
                  }}
                  placeholder="you@example.com"
                  readOnly={Boolean(currentUser)}
                  required
                  type="email"
                  value={form.email}
                />
                {validationError?.field === 'email' ? <p className="field-error" id="email-error" role="alert">{validationError.message}</p> : null}
                <p className="subscription-note" id="email-hint">{currentUser ? 'You are editing the profile for this signed-in account.' : 'We will send a one-time link to verify your address and give you access to your saved choices.'}</p>
                {!signInOnly ? <>
                  <ReviewList form={form} onEdit={editReviewSection} />
                  <p className="subscription-note">Save your profile before checking plans. Extra preferences guide ranking; they do not guarantee an event’s suitability. Checking plans sends no email.</p>
                </> : null}
              </>
            ) : null}

            {notice ? <p className="status-message" role="status">{notice}</p> : null}
            {error ? <p className="error-message" role="alert" ref={requestErrorRef} tabIndex="-1">{error}</p> : null}
            {step === STEPS.length - 1 && !currentUser && !signInOnly ? (
              <button className="resume-button" disabled={busy} onClick={resume} type="button">{existingAccountEmail === form.email.trim() ? 'Email me a sign-in link' : 'Already registered? Send a sign-in link'}</button>
            ) : null}
          </section>

          <div className="form-actions">
            <button className="back-button" disabled={busy || step === 0} onClick={() => {
              setError('');
              setValidationError(null);
              setStep((value) => signInOnly ? 0 : returnToReview ? 3 : Math.max(0, value - 1));
              setSignInOnly(false);
              setReturnToReview(false);
            }} type="button">{signInOnly ? 'Back to choices' : 'Back'}</button>
            <button className="next-button" disabled={busy} type="submit">
              {busy ? signInOnly ? 'Sending…' : 'Saving…' : signInOnly ? 'Email me a sign-in link' : step === STEPS.length - 1 ? 'Save my profile' : returnToReview ? 'Review my choices' : 'Continue'}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
