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
  buildPersonalizationProfile,
  hydrateFormState
} from '../pages/src/profile.js';

describe('personalisation onboarding contract', () => {
  test('returns field-specific errors for every required onboarding selection', () => {
    expect(validateOnboardingStep(0, { ...DEFAULT_FORM_STATE, email: 'not-an-email' })).toEqual({
      field: 'email',
      message: 'Enter a valid email address.'
    });
    expect(validateOnboardingStep(2, { ...DEFAULT_FORM_STATE, locations: [] }).field).toBe('locations');
    expect(validateOnboardingStep(3, { ...DEFAULT_FORM_STATE, interests: [] }).field).toBe('interests');
    expect(validateOnboardingStep(0, { ...DEFAULT_FORM_STATE, email: 'family@example.com' })).toBeNull();
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
    const profile = buildPersonalizationProfile(DEFAULT_FORM_STATE);

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
    const profile = buildPersonalizationProfile(DEFAULT_FORM_STATE);
    const hydrated = hydrateFormState('family@example.com', JSON.stringify(profile));

    expect(hydrated.email).toBe('family@example.com');
    expect(hydrated.audience).toBe(DEFAULT_FORM_STATE.audience);
    expect(hydrated.locations).toEqual(DEFAULT_FORM_STATE.locations);
    expect(hydrated.interests).toEqual(DEFAULT_FORM_STATE.interests);
    expect(hydrated.positiveSignals).toEqual(DEFAULT_FORM_STATE.positiveSignals);
    expect(hydrated.negativeSignals).toEqual(DEFAULT_FORM_STATE.negativeSignals);
    expect(hydrated.seasonalAnchors).toEqual(DEFAULT_FORM_STATE.seasonalAnchors);
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
    expect(payload.summary).toMatchObject({ dry_run: true, sent_count: 0 });
  });
});
