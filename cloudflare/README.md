# Cloudflare Frontend + Worker API

This folder contains a Cloudflare-compatible user dashboard implementation:

- `pages/public/`: Static dashboard assets for Cloudflare Pages.
- `worker/src/`: Cloudflare Worker API with D1-backed user/session storage.

## API Endpoints

- `POST /api/register`
- `POST /api/login`
- `POST /api/logout`
- `GET /api/me`
- `PATCH /api/preferences`

All authenticated calls use an `HttpOnly` session cookie set by register/login.

## D1 Setup

Apply schema in `worker/src/schema.sql` to your D1 database.

## Local test run

```bash
cd cloudflare
npm install
npm test
```

## Deployment model

1. Deploy `pages/public` to Cloudflare Pages.
2. Deploy `worker/src/index.js` as a Worker bound to D1.
3. Route `/api/*` on your Pages domain to the Worker.
