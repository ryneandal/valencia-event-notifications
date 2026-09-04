import { useEffect, useMemo, useRef, useState } from 'react';

import {
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

const STEPS = [
  { eyebrow: 'Welcome', title: 'Where should we send tomorrow?', intro: 'One thoughtful email. No feed to keep up with.' },
  { eyebrow: 'Your people', title: 'Who are we planning for?', intro: 'This helps Brisa understand pace, format, and who needs to enjoy the plan.' },
  { eyebrow: 'Your radius', title: 'How far should we look?', intro: 'Choose every area that feels realistic for a next-day plan.' },
  { eyebrow: 'Your spark', title: 'What makes a day feel worth it?', intro: 'Choose at least one cluster. The details are passed directly to the event ranker.' },
  { eyebrow: 'The practical bits', title: 'More of this. Less of that.', intro: 'These signals help distinguish a technically relevant event from a genuinely good fit.' },
  { eyebrow: 'Local rhythm', title: 'Which traditions should stay on the radar?', intro: 'Brisa will use the selected seasonal anchors when they are relevant.' },
  { eyebrow: 'Review', title: 'This feels like you.', intro: 'We will store this exact profile and use it to shape each digest.' }
];

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
          A next-day events digest shaped around your people, your pace, and the
          parts of València that make you curious.
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

function ReviewList({ form }) {
  const audience = AUDIENCE_OPTIONS.find(({ value }) => value === form.audience)?.label;
  const locations = LOCATION_OPTIONS.filter(({ value }) => form.locations.includes(value)).map(({ label }) => label);
  const interests = INTEREST_CLUSTERS.filter(({ name }) => form.interests.includes(name)).map(({ label }) => label);
  const anchors = SEASONAL_ANCHORS.filter(({ name }) => form.seasonalAnchors.includes(name)).map(({ label }) => label);

  return (
    <div className="review-card">
      {[
        ['Email', form.email],
        ['Planning for', audience],
        ['Search area', locations.join(', ')],
        ['Interests', interests.join(', ')],
        ['Priorities', `${form.positiveSignals.length} positive signals`],
        ['Avoid', `${form.negativeSignals.length} negative signals`],
        ['Calendar', anchors.length ? anchors.join(', ') : 'No seasonal anchors']
      ].map(([label, value]) => (
        <div className="review-row" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const initialized = useRef(false);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(DEFAULT_FORM_STATE);
  const [currentUser, setCurrentUser] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [completion, setCompletion] = useState(null);
  const [preview, setPreview] = useState(null);

  const profile = useMemo(() => buildPersonalizationProfile(form), [form]);
  const current = STEPS[step];

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    const url = new URL(window.location.href);
    if (url.pathname === '/auth/verify') {
      const token = url.searchParams.get('token');
      if (!token) {
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
        .catch((requestError) => setError(requestError.message))
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

  const updateList = (field, value) => {
    setForm((previous) => ({ ...previous, [field]: toggleValue(previous[field], value) }));
  };

  const validateStep = () => {
    if (step === 0 && !/^\S+@\S+\.\S+$/.test(form.email)) return 'Enter a valid email address.';
    if (step === 2 && form.locations.length === 0) return 'Choose at least one search area.';
    if (step === 3 && form.interests.length === 0) return 'Choose at least one interest cluster.';
    return '';
  };

  const goNext = async () => {
    setError('');
    const validationError = validateStep();
    if (validationError) {
      setError(validationError);
      return;
    }
    if (step < STEPS.length - 1) {
      setStep((value) => value + 1);
      return;
    }

    setBusy(true);
    try {
      const payload = currentUser
        ? await updateUserProfile(profile)
        : await registerUser(form.email.trim(), profile);
      setCurrentUser(payload.user);
      if (currentUser) {
        setCompletion({ kind: 'saved', email: payload.user.email });
        setNotice('Your personalisation profile is saved.');
      } else {
        setCompletion({ kind: 'link-sent', email: form.email.trim() });
        setNotice('Check your inbox to confirm your subscription.');
      }
    } catch (requestError) {
      setError(
        requestError.status === 409
          ? 'That email is already registered. Resume the existing setup from the first step.'
          : requestError.message
      );
    } finally {
      setBusy(false);
    }
  };

  const resume = async () => {
    setError('');
    if (!/^\S+@\S+\.\S+$/.test(form.email)) {
      setError('Enter your email first.');
      return;
    }
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
    setBusy(true);
    try {
      await logoutUser();
      setCurrentUser(null);
      setForm(DEFAULT_FORM_STATE);
      setStep(0);
      setCompletion(null);
      setNotice('Signed out.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const changeSubscription = async (subscribed) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const { user } = await updateSubscription(subscribed);
      setCurrentUser(user);
      setCompletion({ kind: 'account', email: user.email });
      setNotice(
        subscribed
          ? 'Your next-day digest is active again.'
          : 'Emails are paused. Your saved profile is still here whenever you return.'
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const previewDigest = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    setPreview(null);
    try {
      const { summary } = await runDigestPreview();
      setPreview(summary);
      setNotice(
        summary.event_count
          ? `Preview ready: ${summary.event_count} event${summary.event_count === 1 ? '' : 's'} found for tomorrow. No email was sent.`
          : 'Preview completed safely, but the current sources did not find an event for tomorrow. No email was sent.'
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  if (completion) {
    const awaitingVerification = completion.kind === 'link-sent';
    const justVerified = completion.kind === 'verified';
    const subscribed = currentUser?.is_subscribed !== false;
    return (
      <main className="onboarding-shell">
        <StoryPanel />
        <section className="form-panel success-screen" aria-live="polite">
          <div className="success-mark" aria-hidden="true">✦</div>
          <p className="eyebrow">
            {awaitingVerification
              ? 'CHECK YOUR INBOX'
              : !subscribed
                ? 'DIGEST PAUSED'
                : justVerified
                  ? 'EMAIL VERIFIED'
                  : 'YOUR BRISA ACCOUNT'}
          </p>
          <h2>
            {awaitingVerification
              ? 'One quick step remains.'
              : subscribed
                ? 'Tomorrow just became easier.'
                : 'Your inbox is taking a breather.'}
          </h2>
          <p>
            {awaitingVerification ? (
              <>We sent a secure, one-time link to <strong>{completion.email}</strong>. Open it to activate your digest.</>
            ) : !subscribed ? (
              <>The digest for <strong>{completion.email}</strong> is paused. Your profile remains saved, and you can resume without repeating onboarding.</>
            ) : (
              <>The personalisation profile for <strong>{completion.email}</strong> will guide the event ranking used to prepare the email digest.</>
            )}
          </p>
          {notice ? <p className="status-message" role="status">{notice}</p> : null}
          {error ? <p className="error-message" role="alert">{error}</p> : null}
          <div className="success-actions">
            {awaitingVerification ? (
              <button className="next-button" onClick={() => { setCompletion(null); setStep(0); }} type="button">Use another email</button>
            ) : (
              <button className="next-button" onClick={() => { setCompletion(null); setStep(1); }} type="button">Edit my profile</button>
            )}
            {currentUser && subscribed ? (
              <button className="back-button" disabled={busy} onClick={previewDigest} type="button">
                {busy ? 'Preparing…' : 'Preview tomorrow safely'}
              </button>
            ) : null}
            {currentUser ? (
              <button
                className="back-button"
                disabled={busy}
                onClick={() => changeSubscription(!subscribed)}
                type="button"
              >
                {busy ? 'Updating…' : subscribed ? 'Pause email digest' : 'Resume email digest'}
              </button>
            ) : null}
            {currentUser ? <button className="text-button" disabled={busy} onClick={signOut} type="button">Sign out</button> : null}
          </div>
          {preview ? <p className="subscription-note">Preview reference: {preview.correlation_id}. Rendered {preview.rendered_count} private preview; sent {preview.sent_count} emails.</p> : null}
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
          <span className="step-label">Step {String(step + 1).padStart(2, '0')} <span>of {String(STEPS.length).padStart(2, '0')}</span></span>
          {currentUser ? <button className="text-button" disabled={busy} onClick={signOut} type="button">Sign out</button> : null}
        </header>
        <div className="progress-track" aria-hidden="true">
          <div className="progress-bar" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
        </div>

        <div className="form-inner">
          <section className="step is-current" aria-labelledby="step-title">
            <p className="eyebrow">{current.eyebrow}</p>
            <h2 id="step-title">{current.title}</h2>
            <p className="step-intro">{current.intro}</p>

            {step === 0 ? (
              <>
                <label className="field-label" htmlFor="email">Email address</label>
                <input
                  autoComplete="email"
                  className="text-input"
                  id="email"
                  onChange={(event) => setForm((previous) => ({ ...previous, email: event.target.value }))}
                  placeholder="you@example.com"
                  type="email"
                  value={form.email}
                />
                <div className="reassurance"><span>☼</span><p><strong>Your inbox stays calm.</strong><br />This address is used for your digest and account access.</p></div>
                {!currentUser ? <button className="resume-button" disabled={busy} onClick={resume} type="button">Already registered? Resume setup</button> : null}
              </>
            ) : null}

            {step === 1 ? (
              <fieldset className="choice-grid">
                <legend className="sr-only">Choose who the digest is for</legend>
                {AUDIENCE_OPTIONS.map((option) => (
                  <ChoiceCard key={option.value} {...option} checked={form.audience === option.value} name="audience" onChange={(audience) => setForm((previous) => ({ ...previous, audience }))} />
                ))}
              </fieldset>
            ) : null}

            {step === 2 ? (
              <fieldset className="choice-grid location-grid">
                <legend className="sr-only">Choose location scope</legend>
                {LOCATION_OPTIONS.map(({ value, label, detail }) => (
                  <ToggleChip key={value} checked={form.locations.includes(value)} icon="⌖" label={<><strong>{label}</strong><small>{detail}</small></>} onChange={() => updateList('locations', value)} />
                ))}
              </fieldset>
            ) : null}

            {step === 3 ? (
              <fieldset className="interest-grid">
                <legend className="sr-only">Choose interest clusters</legend>
                {INTEREST_CLUSTERS.map(({ name, label, icon, includes }) => (
                  <ToggleChip key={name} checked={form.interests.includes(name)} icon={icon} label={<><strong>{label}</strong><small>{includes.slice(0, 3).join(' · ')}</small></>} onChange={() => updateList('interests', name)} />
                ))}
              </fieldset>
            ) : null}

            {step === 4 ? (
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
            ) : null}

            {step === 5 ? (
              <fieldset className="season-grid">
                <legend className="sr-only">Choose seasonal anchors</legend>
                {SEASONAL_ANCHORS.map(({ name, label, months, notes }) => (
                  <ToggleChip key={name} checked={form.seasonalAnchors.includes(name)} icon="☼" label={<><strong>{label}</strong><small>{months.join(' / ')} · {notes}</small></>} onChange={() => updateList('seasonalAnchors', name)} />
                ))}
              </fieldset>
            ) : null}

            {step === 6 ? <ReviewList form={form} /> : null}

            {notice ? <p className="status-message" role="status">{notice}</p> : null}
            {error ? <p className="error-message" role="alert">{error}</p> : null}
          </section>

          <div className="form-actions">
            <button className="back-button" disabled={busy || step === 0} onClick={() => { setError(''); setStep((value) => Math.max(0, value - 1)); }} type="button">Back</button>
            <button className="next-button" disabled={busy} onClick={goNext} type="button">
              {busy ? 'Saving…' : step === STEPS.length - 1 ? 'Save my profile' : 'Continue'}
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
