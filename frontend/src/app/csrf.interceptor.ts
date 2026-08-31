import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../environments/environment';
import { apiUrl } from './api-url';

const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const csrfCookieName = 'mini_rag_csrf';
const csrfHeaderName = 'X-CSRF-Token';

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  const cookie = document.cookie.split('; ').find((entry) => entry.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

/** Sends BFF cookies and mirrors the readable CSRF cookie for unsafe API calls. */
export const bffSessionInterceptor: HttpInterceptorFn = (request, next) => {
  const apiPrefix = apiUrl('/api/');
  if (!request.url.startsWith(apiPrefix)) {
    return next(request);
  }

  let outgoing = request.clone({ withCredentials: true });
  if (!environment.manualDevelopmentTokenEnabled && unsafeMethods.has(request.method.toUpperCase())) {
    const csrfToken = readCookie(csrfCookieName);
    if (csrfToken) {
      outgoing = outgoing.clone({ headers: outgoing.headers.set(csrfHeaderName, csrfToken) });
    }
  }
  return next(outgoing);
};
