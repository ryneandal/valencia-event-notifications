function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

async function apiFetch(fetchImpl, path, options = {}) {
  const response = await fetchImpl(path, {
    credentials: 'include',
    headers: {
      'content-type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.error || `Request failed (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

export function createDashboardApp({ document, fetchImpl }) {
  const statusEl = document.getElementById('status');
  const profileOutputEl = document.getElementById('profile-output');

  function setStatus(message, isError = false) {
    statusEl.textContent = message;
    statusEl.style.color = isError ? '#a3142f' : '#184d43';
  }

  async function refreshProfile() {
    const payload = await apiFetch(fetchImpl, '/api/me', { method: 'GET' });
    profileOutputEl.textContent = prettyJson(payload.user);
    return payload;
  }

  document.getElementById('register-form').addEventListener('submit', async (event) => {
    event.preventDefault();

    const email = document.getElementById('register-email').value;
    const preferencesBlob = document.getElementById('register-preferences').value || null;

    try {
      const payload = await apiFetch(fetchImpl, '/api/register', {
        method: 'POST',
        body: JSON.stringify({ email, preferences_blob: preferencesBlob })
      });
      profileOutputEl.textContent = prettyJson(payload.user);
      setStatus('Registered and signed in.');
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();

    const email = document.getElementById('login-email').value;

    try {
      const payload = await apiFetch(fetchImpl, '/api/login', {
        method: 'POST',
        body: JSON.stringify({ email })
      });
      profileOutputEl.textContent = prettyJson(payload.user);
      setStatus('Logged in.');
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById('preferences-form').addEventListener('submit', async (event) => {
    event.preventDefault();

    const preferencesBlob = document.getElementById('preferences-blob').value || null;

    try {
      const payload = await apiFetch(fetchImpl, '/api/preferences', {
        method: 'PATCH',
        body: JSON.stringify({ preferences_blob: preferencesBlob })
      });
      profileOutputEl.textContent = prettyJson(payload.user);
      setStatus('Preferences saved.');
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById('me-button').addEventListener('click', async () => {
    try {
      await refreshProfile();
      setStatus('Profile refreshed.');
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById('logout-button').addEventListener('click', async () => {
    try {
      await apiFetch(fetchImpl, '/api/logout', { method: 'POST' });
      profileOutputEl.textContent = 'No profile loaded.';
      setStatus('Logged out.');
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  return {
    refreshProfile
  };
}

if (typeof window !== 'undefined') {
  createDashboardApp({ document: window.document, fetchImpl: window.fetch.bind(window) });
}
