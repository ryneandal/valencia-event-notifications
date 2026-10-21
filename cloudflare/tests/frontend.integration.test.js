import { describe, expect, test, vi } from 'vitest';

import {
  apiFetch,
  registerUser,
  runDigestPreview,
  updateSubscription,
  updateUserProfile,
  verifyMagicLink
} from '../pages/src/api.js';
import { validateOnboardingStep } from '../pages/src/onboarding.js';
import {
  DEFAULT_FORM_STATE,
  INTEREST_CLUSTERS,
  LOCATION_OPTIONS,
  NEGATIVE_SIGNAL_OPTIONS,
  POSITIVE_SIGNAL_OPTIONS,
  SEASONAL_ANCHORS,
  buildPersonalizationProfile,
  hydrateFormState
} from '../pages/src/profile.js';

const chosenForm = {
  ...DEFAULT_FORM_STATE,
  audience: 'family_with_school_age_kids',
  interests: ['local_festivals_spectacle', 'parks_and_play'],
  positiveSignals: ['interactive', 'outdoors', 'daytime', 'near_transit'],
  negativeSignals: ['starts_after_20', 'crowd_extreme'],
  seasonalAnchors: ['Fallas', 'Gran_Feria_de_Julio']
};

describe('personalisation onboarding contract', () => {
  test('starts without an audience, event types, or optional family assumptions', () => {
    expect(DEFAULT_FORM_STATE).toMatchObject({
      audience: '', interests: [], positiveSignals: [], negativeSignals: [], seasonalAnchors: []
    });
    expect(DEFAULT_FORM_STATE.locations).toEqual(['Valencia city']);
    expect(hydrateFormState('new@example.com', null)).toEqual({ ...DEFAULT_FORM_STATE, email: 'new@example.com' });
  });

  test('returns field-specific errors for every required onboarding selection', () => {
    expect(validateOnboardingStep(0, DEFAULT_FORM_STATE).field).toBe('audience');
    expect(validateOnboardingStep(3, { ...chosenForm, email: 'not-an-email' })).toEqual({
      field: 'email',
      message: 'Enter a valid email address.'
    });
    expect(validateOnboardingStep(0, { ...chosenForm, locations: [] }).field).toBe('locations');
    expect(validateOnboardingStep(1, { ...chosenForm, interests: [] }).field).toBe('interests');
    expect(validateOnboardingStep(0, chosenForm)).toBeNull();
    expect(validateOnboardingStep(2, DEFAULT_FORM_STATE)).toBeNull();
    expect(validateOnboardingStep(3, { ...chosenForm, email: 'family@example.com' })).toBeNull();
  });

  test.each([
    [422, 'invalid_input', false],
    [503, 'service', true]
  ])('classifies API status %s as %s', async (status, kind, retryable) => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ error: 'backend detail' }), {
        status,
        headers: { 'content-type': 'application/json' }
      })
    );

    await expect(apiFetch('/api/example', {}, fetchImpl)).rejects.toMatchObject({
      status,
      kind,
      retryable
    });
  });

  test('classifies network failures as retryable service errors', async () => {
    const fetchImpl = vi.fn(async () => { throw new TypeError('offline'); });
    await expect(apiFetch('/api/example', {}, fetchImpl)).rejects.toMatchObject({
      status: 0,
      kind: 'service',
      retryable: true,
      message: 'We could not reach Brisa. Check your connection and try again.'
    });
  });

  test('builds the exact profile shape consumed by the Python ranker', () => {
    const profile = buildPersonalizationProfile(chosenForm);

    expect(Object.keys(profile)).toEqual([
      'audience',
      'location_scope',
      'top_interest_clusters',
      'strong_positive_signals',
      'strong_negative_signals',
      'seasonal_anchors'
    ]);
    expect(profile.audience).toBe('family_with_school_age_kids');
    expect(profile.location_scope).toEqual(['Valencia city']);
    expect(profile.top_interest_clusters[0]).toEqual({
      name: 'local_festivals_spectacle',
      includes: INTEREST_CLUSTERS[0].includes
    });
    expect(profile.strong_positive_signals).toContain('near_transit');
    expect(profile.strong_negative_signals).toContain('starts_after_20');
    expect(profile.seasonal_anchors[0]).toMatchObject({ name: 'Fallas' });
  });

  test('hydrates a saved profile without renaming or dropping selections', () => {
    const profile = buildPersonalizationProfile(chosenForm);
    const hydrated = hydrateFormState('family@example.com', JSON.stringify(profile));

    expect(hydrated.email).toBe('family@example.com');
    expect(hydrated.audience).toBe(chosenForm.audience);
    expect(hydrated.locations).toEqual(chosenForm.locations);
    expect(hydrated.interests).toEqual(chosenForm.interests);
    expect(hydrated.positiveSignals).toEqual(chosenForm.positiveSignals);
    expect(hydrated.negativeSignals).toEqual(chosenForm.negativeSignals);
    expect(hydrated.seasonalAnchors).toEqual(chosenForm.seasonalAnchors);
  });

  test('preserves every supported saved field, including older area preferences', () => {
    const saved = buildPersonalizationProfile({
      ...chosenForm,
      locations: LOCATION_OPTIONS.map(({ value }) => value),
      interests: INTEREST_CLUSTERS.map(({ name }) => name),
      positiveSignals: POSITIVE_SIGNAL_OPTIONS.map(([value]) => value),
      negativeSignals: NEGATIVE_SIGNAL_OPTIONS.map(([value]) => value),
      seasonalAnchors: SEASONAL_ANCHORS.map(({ name }) => name)
    });
    const restored = hydrateFormState('reader@example.com', JSON.stringify(saved));
    expect(buildPersonalizationProfile(restored)).toEqual(saved);
  });

  test('round-trips every bounded event type and discards unsupported saved choices', () => {
    const interests = INTEREST_CLUSTERS.map(({ name }) => name);
    expect(interests).toHaveLength(12);
    expect(new Set(interests).size).toBe(interests.length);
    const profile = buildPersonalizationProfile({ ...DEFAULT_FORM_STATE, interests });
    expect(hydrateFormState('', JSON.stringify(profile)).interests).toEqual(interests);
    profile.top_interest_clusters = [
      { name: 'live_music' }, { name: 'custom_type' }, { name: 'live_music' }, null
    ];
    expect(hydrateFormState('', JSON.stringify(profile)).interests).toEqual(['live_music']);
    profile.top_interest_clusters = [{ name: 'custom_type' }];
    expect(hydrateFormState('', JSON.stringify(profile)).interests).toEqual([]);
  });

  test.each([[], ['custom_type'], ['live_music', 'live_music'], Array(13).fill('film')])(
    'rejects an empty or unsupported event-type selection: %j', (interests) => {
      expect(validateOnboardingStep(1, { ...DEFAULT_FORM_STATE, interests })).toEqual({
        field: 'interests', message: 'Choose at least one event type from the list.'
      });
    }
  );

  test('builds selections from catalog definitions only', () => {
    const profile = buildPersonalizationProfile({
      ...DEFAULT_FORM_STATE, interests: ['live_music', 'custom_type', 'live_music']
    });
    expect(profile.top_interest_clusters).toEqual([{
      name: 'live_music', includes: ['concerts', 'live bands', 'jazz', 'classical music', 'DJ sets']
    }]);
  });

  test('registers with the profile serialized into preferences_blob', async () => {
    const profile = buildPersonalizationProfile(DEFAULT_FORM_STATE);
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true, message: 'Check your email to continue' }), {
        status: 202,
        headers: { 'content-type': 'application/json' }
      })
    );

    await registerUser('family@example.com', profile, fetchImpl);

    expect(fetchImpl).toHaveBeenCalledOnce();
    const [path, options] = fetchImpl.mock.calls[0];
    expect(path).toBe('/api/register');
    expect(options.credentials).toBe('include');
    expect(JSON.parse(options.body)).toEqual({
      email: 'family@example.com',
      preferences_blob: JSON.stringify(profile)
    });
  });

  test('exchanges a magic-link token without putting it in the URL', async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ user: { email: 'family@example.com' } }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    await verifyMagicLink('one-time-token', fetchImpl);

    const [path, options] = fetchImpl.mock.calls[0];
    expect(path).toBe('/api/auth/verify');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ token: 'one-time-token' });
    expect(options.credentials).toBe('include');
  });

  test('updates an existing user with the same lossless profile payload', async () => {
    const profile = buildPersonalizationProfile(DEFAULT_FORM_STATE);
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ user: { email: 'family@example.com' } }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    await updateUserProfile(profile, fetchImpl);

    const [path, options] = fetchImpl.mock.calls[0];
    expect(path).toBe('/api/preferences');
    expect(options.method).toBe('PATCH');
    expect(JSON.parse(options.body).preferences_blob).toBe(JSON.stringify(profile));
  });

  test.each([false, true])(
    'updates subscription state with an authenticated same-origin request: %s',
    async (subscribed) => {
      const fetchImpl = vi.fn(async () =>
        new Response(
          JSON.stringify({
            user: { email: 'family@example.com', is_subscribed: subscribed }
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      );

      const payload = await updateSubscription(subscribed, fetchImpl);

      const [path, options] = fetchImpl.mock.calls[0];
      expect(path).toBe('/api/subscription');
      expect(options.method).toBe('PATCH');
      expect(options.credentials).toBe('include');
      expect(JSON.parse(options.body)).toEqual({ subscribed });
      expect(payload.user.is_subscribed).toBe(subscribed);
    }
  );

  test('runs an authenticated digest preview that defaults to no delivery', async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          summary: {
            correlation_id: 'safe-reference',
            dry_run: true,
            event_count: 2,
            rendered_count: 1,
            sent_count: 0
          }
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      )
    );

    const payload = await runDigestPreview(fetchImpl);

    const [path, options] = fetchImpl.mock.calls[0];
    expect(path).toBe('/api/digest/dry-run');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('include');
    expect(options.body).toBeUndefined();
    expect(payload.summary).toMatchObject({ dry_run: true, sent_count: 0 });
  });

  test('sends only the chosen date and preserves cancellation for a future preview', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ summary: {} }), { status: 200 }));
    const controller = new AbortController();
    await runDigestPreview(fetchImpl, { date: '2026-10-25', signal: controller.signal });
    const [path, options] = fetchImpl.mock.calls[0];
    expect(path).toBe('/api/digest/dry-run');
    expect(JSON.parse(options.body)).toEqual({ date: '2026-10-25' });
    expect(options.signal).toBe(controller.signal);
    expect(options.credentials).toBe('include');
  });
});
