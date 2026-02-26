const SESSION_COOKIE_NAME = 've_session';
const DEFAULT_SESSION_TTL_HOURS = 24;

function jsonResponse(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      ...extraHeaders
    }
  });
}

function normalizeEmail(email) {
  if (typeof email !== 'string') {
    throw new Error('Invalid email');
  }

  const normalized = email.trim().toLowerCase();
  if (!normalized || !normalized.includes('@')) {
    throw new Error('Invalid email');
  }

  return normalized;
}

function parseCookieHeader(cookieHeader) {
  const parsed = {};
  if (!cookieHeader) {
    return parsed;
  }

  const parts = cookieHeader.split(';');
  for (const part of parts) {
    const [rawKey, ...rest] = part.trim().split('=');
    if (!rawKey || rest.length === 0) {
      continue;
    }
    parsed[rawKey] = rest.join('=');
  }
  return parsed;
}

function cookieOptions({ maxAgeSeconds }) {
  return [
    'Path=/',
    'HttpOnly',
    'Secure',
    'SameSite=Lax',
    `Max-Age=${maxAgeSeconds}`
  ].join('; ');
}

function clearCookieOptions() {
  return ['Path=/', 'HttpOnly', 'Secure', 'SameSite=Lax', 'Max-Age=0'].join('; ');
}

function hex(bytes) {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

async function sha256Hex(value) {
  const encoder = new TextEncoder();
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(value));
  return hex(new Uint8Array(digest));
}

function randomToken() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  const raw = String.fromCharCode(...bytes);
  const encoded = typeof btoa === 'function' ? btoa(raw) : Buffer.from(raw, 'binary').toString('base64');
  return encoded
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function createSession(env, userId, ttlHours) {
  const token = randomToken();
  const tokenHash = await sha256Hex(token);
  const ttlClause = ttlHours >= 0 ? `+${ttlHours} hours` : `${ttlHours} hours`;

  await env.DB.prepare(
    `
      INSERT INTO sessions (user_id, token_hash, expires_at)
      VALUES (?, ?, datetime('now', ?))
    `
  )
    .bind(userId, tokenHash, ttlClause)
    .run();

  return token;
}

async function resolveSessionUser(env, request) {
  const cookies = parseCookieHeader(request.headers.get('cookie'));
  const sessionToken = cookies[SESSION_COOKIE_NAME];

  if (!sessionToken) {
    return null;
  }

  const tokenHash = await sha256Hex(sessionToken);

  const user = await env.DB.prepare(
    `
      SELECT
        u.id,
        u.email,
        u.preferences_blob,
        u.is_active,
        s.id AS session_id
      FROM sessions AS s
      INNER JOIN users AS u ON u.id = s.user_id
      WHERE s.token_hash = ?
        AND s.expires_at > CURRENT_TIMESTAMP
        AND u.is_active = 1
      LIMIT 1
    `
  )
    .bind(tokenHash)
    .first();

  if (!user) {
    return null;
  }

  return user;
}

function userPayload(user) {
  return {
    id: user.id,
    email: user.email,
    preferences_blob: user.preferences_blob,
    is_active: Boolean(user.is_active)
  };
}

export async function handleRequest(request, env) {
  const url = new URL(request.url);
  const method = request.method.toUpperCase();
  const sessionTtlHours = Number(env.SESSION_TTL_HOURS || DEFAULT_SESSION_TTL_HOURS);

  if (url.pathname === '/api/health' && method === 'GET') {
    return jsonResponse({ ok: true });
  }

  if (url.pathname === '/api/register' && method === 'POST') {
    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResponse({ error: 'Invalid JSON payload' }, 400);
    }

    const preferencesBlob = payload?.preferences_blob ?? null;

    let email;
    try {
      email = normalizeEmail(payload?.email);
    } catch {
      return jsonResponse({ error: 'Invalid email' }, 400);
    }

    try {
      await env.DB.prepare(
        `
          INSERT INTO users (email, preferences_blob)
          VALUES (?, ?)
        `
      )
        .bind(email, preferencesBlob)
        .run();
    } catch {
      return jsonResponse({ error: 'User already exists' }, 409);
    }

    const user = await env.DB.prepare(
      `
        SELECT id, email, preferences_blob, is_active
        FROM users
        WHERE email = ?
        LIMIT 1
      `
    )
      .bind(email)
      .first();

    const token = await createSession(env, user.id, sessionTtlHours);

    return jsonResponse(
      { user: userPayload(user) },
      201,
      {
        'set-cookie': `${SESSION_COOKIE_NAME}=${token}; ${cookieOptions({ maxAgeSeconds: sessionTtlHours * 3600 })}`
      }
    );
  }

  if (url.pathname === '/api/login' && method === 'POST') {
    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResponse({ error: 'Invalid JSON payload' }, 400);
    }

    let email;
    try {
      email = normalizeEmail(payload?.email);
    } catch {
      return jsonResponse({ error: 'Invalid email' }, 400);
    }

    const user = await env.DB.prepare(
      `
        SELECT id, email, preferences_blob, is_active
        FROM users
        WHERE email = ?
        LIMIT 1
      `
    )
      .bind(email)
      .first();

    if (!user || !user.is_active) {
      return jsonResponse({ error: 'User not found' }, 404);
    }

    const token = await createSession(env, user.id, sessionTtlHours);

    return jsonResponse(
      { user: userPayload(user) },
      200,
      {
        'set-cookie': `${SESSION_COOKIE_NAME}=${token}; ${cookieOptions({ maxAgeSeconds: sessionTtlHours * 3600 })}`
      }
    );
  }

  if (url.pathname === '/api/logout' && method === 'POST') {
    const user = await resolveSessionUser(env, request);
    if (user) {
      const cookies = parseCookieHeader(request.headers.get('cookie'));
      const sessionToken = cookies[SESSION_COOKIE_NAME];
      if (sessionToken) {
        const tokenHash = await sha256Hex(sessionToken);
        await env.DB.prepare('DELETE FROM sessions WHERE token_hash = ?').bind(tokenHash).run();
      }
    }

    return jsonResponse(
      { ok: true },
      200,
      { 'set-cookie': `${SESSION_COOKIE_NAME}=; ${clearCookieOptions()}` }
    );
  }

  if (url.pathname === '/api/me' && method === 'GET') {
    const user = await resolveSessionUser(env, request);
    if (!user) {
      return jsonResponse({ error: 'Unauthorized' }, 401);
    }

    return jsonResponse({ user: userPayload(user) });
  }

  if (url.pathname === '/api/preferences' && method === 'PATCH') {
    const user = await resolveSessionUser(env, request);
    if (!user) {
      return jsonResponse({ error: 'Unauthorized' }, 401);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResponse({ error: 'Invalid JSON payload' }, 400);
    }

    const preferencesBlob = payload?.preferences_blob ?? null;

    await env.DB.prepare('UPDATE users SET preferences_blob = ? WHERE id = ?')
      .bind(preferencesBlob, user.id)
      .run();

    const updated = await env.DB.prepare(
      `
        SELECT id, email, preferences_blob, is_active
        FROM users
        WHERE id = ?
        LIMIT 1
      `
    )
      .bind(user.id)
      .first();

    return jsonResponse({ user: userPayload(updated) });
  }

  return jsonResponse({ error: 'Not found' }, 404);
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  }
};
