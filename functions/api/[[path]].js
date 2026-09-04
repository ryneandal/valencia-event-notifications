const DEFAULT_API_BASE_URL = 'https://valencia-events-api.ryne.workers.dev';

export function proxyApiRequest(request, apiBaseUrl = DEFAULT_API_BASE_URL, fetchImpl = fetch) {
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`${incomingUrl.pathname}${incomingUrl.search}`, apiBaseUrl);

  return fetchImpl(new Request(targetUrl, request));
}

export function onRequest({ request, env }) {
  return proxyApiRequest(request, env.API_BASE_URL || DEFAULT_API_BASE_URL);
}
