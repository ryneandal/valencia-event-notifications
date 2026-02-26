import { describe, expect, test } from 'vitest';

import { handleRequest } from '../worker/src/index.js';

class InMemoryD1 {
  constructor() {
    this.users = [];
    this.sessions = [];
    this.userId = 0;
    this.sessionId = 0;
  }

  prepare(sql) {
    return new InMemoryStatement(this, sql);
  }
}

class InMemoryStatement {
  constructor(state, sql) {
    this.state = state;
    this.sql = sql.replace(/\s+/g, ' ').trim();
    this.params = [];
  }

  bind(...params) {
    this.params = params;
    return this;
  }

  async run() {
    const sql = this.sql;

    if (sql.startsWith('INSERT INTO users (email, preferences_blob)')) {
      const [email, preferencesBlob] = this.params;
      if (this.state.users.some((user) => user.email === email)) {
        throw new Error('UNIQUE constraint failed: users.email');
      }

      const user = {
        id: ++this.state.userId,
        email,
        preferences_blob: preferencesBlob,
        is_active: 1
      };
      this.state.users.push(user);

      return {
        success: true,
        meta: { changes: 1, last_row_id: user.id }
      };
    }

    if (sql.startsWith('INSERT INTO sessions (user_id, token_hash, expires_at)')) {
      const [userId, tokenHash, ttlClause] = this.params;
      const hours = Number(ttlClause.replace(' hours', ''));
      const expiresAt = new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();

      const session = {
        id: ++this.state.sessionId,
        user_id: Number(userId),
        token_hash: tokenHash,
        expires_at: expiresAt
      };
      this.state.sessions.push(session);

      return {
        success: true,
        meta: { changes: 1, last_row_id: session.id }
      };
    }

    if (sql.startsWith('UPDATE users SET preferences_blob = ? WHERE id = ?')) {
      const [preferencesBlob, userId] = this.params;
      const user = this.state.users.find((entry) => entry.id === Number(userId));
      if (user) {
        user.preferences_blob = preferencesBlob;
        return { success: true, meta: { changes: 1 } };
      }
      return { success: true, meta: { changes: 0 } };
    }

    if (sql.startsWith('DELETE FROM sessions WHERE token_hash = ?')) {
      const [tokenHash] = this.params;
      const before = this.state.sessions.length;
      this.state.sessions = this.state.sessions.filter(
        (session) => session.token_hash !== tokenHash
      );
      return {
        success: true,
        meta: { changes: before - this.state.sessions.length }
      };
    }

    throw new Error(`Unhandled run SQL: ${sql}`);
  }

  async first() {
    const sql = this.sql;

    if (sql.startsWith('SELECT id, email, preferences_blob, is_active FROM users WHERE email = ?')) {
      const [email] = this.params;
      return this.state.users.find((user) => user.email === email) || null;
    }

    if (sql.startsWith('SELECT id, email, preferences_blob, is_active FROM users WHERE id = ?')) {
      const [userId] = this.params;
      return this.state.users.find((user) => user.id === Number(userId)) || null;
    }

    if (sql.includes('FROM sessions AS s INNER JOIN users AS u')) {
      const [tokenHash] = this.params;
      const session = this.state.sessions.find((entry) => entry.token_hash === tokenHash);
      if (!session) {
        return null;
      }

      const expiresAtMs = Date.parse(session.expires_at);
      if (Number.isNaN(expiresAtMs) || expiresAtMs <= Date.now()) {
        return null;
      }

      const user = this.state.users.find((entry) => entry.id === session.user_id);
      if (!user || !user.is_active) {
        return null;
      }

      return {
        id: user.id,
        email: user.email,
        preferences_blob: user.preferences_blob,
        is_active: user.is_active,
        session_id: session.id
      };
    }

    throw new Error(`Unhandled first SQL: ${sql}`);
  }
}

function env(overrides = {}) {
  return {
    DB: new InMemoryD1(),
    SESSION_TTL_HOURS: '24',
    ...overrides
  };
}

function cookieFromSetCookie(setCookieHeader) {
  return setCookieHeader.split(';')[0];
}

describe('worker integration', () => {
  test('register, me, update preferences', async () => {
    const runtimeEnv = env();

    const registerResponse = await handleRequest(
      new Request('https://example.com/api/register', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          email: '  Family.User@Example.com ',
          preferences_blob: '{"audience":"family"}'
        })
      }),
      runtimeEnv
    );

    expect(registerResponse.status).toBe(201);
    const registerBody = await registerResponse.json();
    expect(registerBody.user.email).toBe('family.user@example.com');
    expect(registerBody.user.preferences_blob).toBe('{"audience":"family"}');

    const setCookie = registerResponse.headers.get('set-cookie');
    expect(setCookie).toContain('ve_session=');
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('Secure');

    const cookie = cookieFromSetCookie(setCookie);

    const meResponse = await handleRequest(
      new Request('https://example.com/api/me', {
        method: 'GET',
        headers: { cookie }
      }),
      runtimeEnv
    );
    expect(meResponse.status).toBe(200);

    const updateResponse = await handleRequest(
      new Request('https://example.com/api/preferences', {
        method: 'PATCH',
        headers: {
          cookie,
          'content-type': 'application/json'
        },
        body: JSON.stringify({ preferences_blob: '{"interests":["music"]}' })
      }),
      runtimeEnv
    );

    expect(updateResponse.status).toBe(200);
    const updateBody = await updateResponse.json();
    expect(updateBody.user.preferences_blob).toBe('{"interests":["music"]}');
  });

  test('duplicate register returns conflict', async () => {
    const runtimeEnv = env();
    const payload = {
      email: 'dup@example.com',
      preferences_blob: null
    };

    const first = await handleRequest(
      new Request('https://example.com/api/register', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload)
      }),
      runtimeEnv
    );
    expect(first.status).toBe(201);

    const second = await handleRequest(
      new Request('https://example.com/api/register', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload)
      }),
      runtimeEnv
    );

    expect(second.status).toBe(409);
  });

  test('missing or invalid session is unauthorized', async () => {
    const runtimeEnv = env();

    const meWithoutCookie = await handleRequest(
      new Request('https://example.com/api/me', { method: 'GET' }),
      runtimeEnv
    );
    expect(meWithoutCookie.status).toBe(401);

    const updateWithInvalidCookie = await handleRequest(
      new Request('https://example.com/api/preferences', {
        method: 'PATCH',
        headers: {
          cookie: 've_session=not-real',
          'content-type': 'application/json'
        },
        body: JSON.stringify({ preferences_blob: '{}' })
      }),
      runtimeEnv
    );
    expect(updateWithInvalidCookie.status).toBe(401);
  });

  test('expired session is rejected', async () => {
    const runtimeEnv = env({ SESSION_TTL_HOURS: '-1' });

    const registerResponse = await handleRequest(
      new Request('https://example.com/api/register', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: 'expired@example.com' })
      }),
      runtimeEnv
    );

    expect(registerResponse.status).toBe(201);
    const cookie = cookieFromSetCookie(registerResponse.headers.get('set-cookie'));

    const meResponse = await handleRequest(
      new Request('https://example.com/api/me', {
        method: 'GET',
        headers: { cookie }
      }),
      runtimeEnv
    );

    expect(meResponse.status).toBe(401);
  });
});
