export class ApiError extends Error {
  constructor(status, data) {
    super(typeof data === 'string' ? data : JSON.stringify(data));
    this.status = status;
    this.data = data;
  }
}

export class ApiClient {
  constructor(fetcher = (...args) => fetch(...args), origin = location.origin) {
    this.fetcher = fetcher;
    this.origin = origin;
    this.csrfToken = null;
  }

  url(path) {
    const url = new URL(path.startsWith('/') || /^https?:/.test(path) ? path : `/api/${path}`, this.origin);
    if (url.origin !== this.origin || !url.pathname.startsWith('/api/')) throw new Error('Invalid API destination');
    return url.pathname + url.search;
  }

  async csrf() {
    if (!this.csrfToken) {
      let response;
      try {
        response = await this.fetcher('/api/auth/csrf/', {
          credentials:'same-origin', cache:'no-store', signal:AbortSignal.timeout(25000),
        });
      } catch { throw new ApiError(0, {}); }
      if (!response.ok) throw new ApiError(response.status, {});
      this.csrfToken = (await response.json()).csrfToken;
      if (!this.csrfToken) throw new ApiError(503, {});
    }
    return this.csrfToken;
  }

  async request(path, method = 'GET', body, signal) {
    const url = this.url(path);
    const headers = {Accept:'application/json'};
    const multipart = Object.prototype.toString.call(body) === '[object FormData]';
    if (!['GET','HEAD'].includes(method)) headers['X-CSRFToken'] = await this.csrf();
    if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort();
    signal?.addEventListener('abort', abort, {once:true});
    const timer = setTimeout(abort, multipart ? 300000 : 25000);
    let response;
    try {
      response = await this.fetcher(url, {
        method, headers, body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
        credentials:'same-origin', cache:'no-store', signal:controller.signal,
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new ApiError(0, {});
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
    }
    if (response.status === 204) return null;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 403) this.csrfToken = null;
      throw new ApiError(response.status, data);
    }
    if (data.csrfToken) this.csrfToken = data.csrfToken;
    return data;
  }

  async all(path, signal) {
    const rows = [];
    const visited = new Set();
    let next = path;
    while (next) {
      const url = this.url(next);
      if (visited.has(url) || visited.size >= 100) throw new ApiError(503, {});
      visited.add(url);
      const result = await this.request(url, 'GET', undefined, signal);
      if (Array.isArray(result)) return result;
      rows.push(...result.results);
      next = result.next;
    }
    return rows;
  }
}
