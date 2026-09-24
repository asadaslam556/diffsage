// Thin fetch wrapper for the gateway.
//
// The access token only lives in memory here. The refresh token is an
// httpOnly cookie the browser sends to /api/auth/refresh on its own, so a
// page reload just calls refresh() to get a new access token.

let accessToken = null;
let refreshing = null; // one in-flight refresh shared by everyone who hit a 401
let onSessionLost = () => {};

export class ApiError extends Error {
  constructor(status, code, message, requestId, headers) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.headers = headers;
  }
}

export function setAccessToken(token) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function onUnauthenticated(fn) {
  onSessionLost = fn;
}

export async function toApiError(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    // proxies sometimes answer with HTML; fall through to a generic message
  }
  const err = body?.error ?? {};
  return new ApiError(
    response.status,
    err.code ?? "http_" + response.status,
    err.message ?? `Request failed (${response.status})`,
    err.request_id,
    response.headers,
  );
}

export function refresh() {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
      .then(async (res) => {
        if (!res.ok) throw await toApiError(res);
        const data = await res.json();
        accessToken = data.access_token;
        return data;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

// fetch with auth + one retry after a silent refresh. Returns the raw
// Response so streaming callers can read the body themselves.
export async function authFetch(path, init = {}, { retry = true } = {}) {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Can't reach the server. Is the backend running?");
  }

  if (response.status === 401 && retry && !path.startsWith("/api/auth/")) {
    try {
      await refresh();
    } catch {
      accessToken = null;
      onSessionLost();
      throw await toApiError(response);
    }
    return authFetch(path, init, { retry: false });
  }
  return response;
}

export async function api(path, { method = "GET", body, signal } = {}) {
  const response = await authFetch(path, {
    method,
    signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return null;
  return response.json();
}
