export async function apiFetch(path, options = {}, fetchImpl = fetch) {
  const response = await fetchImpl(path, {
    credentials: 'include',
    ...options,
    headers: {
      'content-type': 'application/json',
      ...(options.headers || {})
    }
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // A useful status-based message is produced below for empty/non-JSON errors.
  }

  if (!response.ok) {
    const error = new Error(payload?.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }

  return payload;
}

export function loadCurrentUser(fetchImpl = fetch) {
  return apiFetch('/api/me', { method: 'GET' }, fetchImpl);
}

export function registerUser(email, profile, fetchImpl = fetch) {
  return apiFetch(
    '/api/register',
    {
      method: 'POST',
      body: JSON.stringify({ email, preferences_blob: JSON.stringify(profile) })
    },
    fetchImpl
  );
}

export function resumeUser(email, fetchImpl = fetch) {
  return apiFetch(
    '/api/login',
    { method: 'POST', body: JSON.stringify({ email }) },
    fetchImpl
  );
}

export function verifyMagicLink(token, fetchImpl = fetch) {
  return apiFetch(
    '/api/auth/verify',
    { method: 'POST', body: JSON.stringify({ token }) },
    fetchImpl
  );
}

export function updateUserProfile(profile, fetchImpl = fetch) {
  return apiFetch(
    '/api/preferences',
    {
      method: 'PATCH',
      body: JSON.stringify({ preferences_blob: JSON.stringify(profile) })
    },
    fetchImpl
  );
}

export function updateSubscription(subscribed, fetchImpl = fetch) {
  return apiFetch(
    '/api/subscription',
    {
      method: 'PATCH',
      body: JSON.stringify({ subscribed })
    },
    fetchImpl
  );
}

export function runDigestPreview(fetchImpl = fetch) {
  return apiFetch('/api/digest/dry-run', { method: 'POST' }, fetchImpl);
}

export function logoutUser(fetchImpl = fetch) {
  return apiFetch('/api/logout', { method: 'POST' }, fetchImpl);
}
