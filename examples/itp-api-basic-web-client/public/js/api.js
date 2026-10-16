'use strict';

// Requests are tracked so a restarted interaction can cancel outdated calls.
const requests = new Set();

/** Describe failures from the local PHP adapter in a consistent way. */
export class ClientError extends Error {
  constructor(message, code = 'NETWORK_ERROR', status = 0, retryAfterSeconds = null) {
    super(message);
    this.name = 'ClientError';
    this.code = code;
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** Send a same-origin JSON request to api.php and normalize HTTP errors. */
export async function api(action, { method = 'GET', body = null, query = {} } = {}) {
  const controller = new AbortController();
  requests.add(controller);
  const url = new URL('api.php', window.location.href);
  url.searchParams.set('action', action);
  Object.entries(query).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });

  try {
    const response = await fetch(url, {
      method,
      headers: body === null ? {} : { 'Content-Type': 'application/json' },
      body: body === null ? null : JSON.stringify(body),
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new ClientError('The PHP adapter did not return valid JSON.', 'BAD_RESPONSE', response.status);
    }

    if (!response.ok) {
      throw new ClientError(
        data?.error?.message || `HTTP error ${response.status}`,
        data?.error?.code || 'HTTP_ERROR',
        response.status,
        data?.error?.retryAfterSeconds ?? null,
      );
    }

    return data;
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof ClientError) {
      throw error;
    }
    throw new ClientError('The connection to the local PHP adapter failed.');
  } finally {
    requests.delete(controller);
  }
}

/** Abort all pending requests when a new interaction starts. */
export function cancelRequests() {
  for (const controller of requests) {
    controller.abort();
  }
  requests.clear();
}
