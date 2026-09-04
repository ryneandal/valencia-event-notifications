import { describe, expect, test, vi } from 'vitest';

import { registerUser, updateUserProfile, verifyMagicLink } from '../pages/src/api.js';
import {
  DEFAULT_FORM_STATE,
  INTEREST_CLUSTERS,
  buildPersonalizationProfile,
  hydrateFormState
} from '../pages/src/profile.js';

describe('personalisation onboarding contract', () => {
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
});
