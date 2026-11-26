(() => {
  'use strict';

  if (window.__QA_TELEMETRY_INSTALLED__) {
    return window.__QA_TELEMETRY__;
  }
  window.__QA_TELEMETRY_INSTALLED__ = true;

  const MAX_EVENTS = 200;
  const MAX_TEXT = 400;
  const SECRET_URL_PARAM_RE = /([?&](?:token|access_token|refresh_token|code|key|api_key|apikey|secret|password|pwd|jwt|session|auth)=)([^&#]+)/gi;
  const USERINFO_URL_RE = /([a-z][a-z0-9+.-]*:\/\/)([^/\s:@]+:[^/\s@]+)@/gi;
  const BEARER_RE = /\bBearer\s+[A-Za-z0-9\-._~+/]{12,}=*/gi;
  const JWT_RE = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g;
  const SLACK_RE = /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g;
  const STRIPE_RE = /\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b/g;
  const SENSITIVE_KEY_RE = /^(?:password|passwd|pwd|secret|token|access_token|refresh_token|api_key|apikey|client_secret|authorization|cookie|set-cookie|jwt|session)$/i;

  function redactText(value) {
    if (value == null) return '';
    let text = String(value);
    text = text.replace(USERINFO_URL_RE, '$1[REDACTED]@');
    text = text.replace(SECRET_URL_PARAM_RE, '$1[REDACTED]');
    text = text.replace(BEARER_RE, 'Bearer [REDACTED]');
    text = text.replace(JWT_RE, '[REDACTED JWT]');
    text = text.replace(SLACK_RE, '[REDACTED SLACK TOKEN]');
    text = text.replace(STRIPE_RE, '[REDACTED STRIPE KEY]');
    if (text.length > MAX_TEXT) {
      text = text.slice(0, MAX_TEXT - 3) + '...';
    }
    return text;
  }

  function redactJson(obj, depth = 0) {
    if (depth > 4 || obj == null) return obj;
    if (typeof obj === 'string') return redactText(obj);
    if (typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) {
      return obj.slice(0, 20).map((item) => redactJson(item, depth + 1));
    }
    const out = {};
    for (const key of Object.keys(obj).slice(0, 30)) {
      if (SENSITIVE_KEY_RE.test(key)) {
        out[key] = '[REDACTED]';
      } else {
        out[key] = redactJson(obj[key], depth + 1);
      }
    }
    return out;
  }

  function safeFormatArg(arg) {
    if (typeof arg === 'string') return redactText(arg);
    if (arg instanceof Error) return redactText(arg.stack || arg.message || String(arg));
    try {
      return redactText(JSON.stringify(redactJson(arg)));
    } catch (_err) {
      return redactText(String(arg));
    }
  }

  const telemetry = {
    installedAt: new Date().toISOString(),
    consoleErrors: [],
    pageErrors: [],
    unhandledRejections: [],
    networkFailures: [],
    graphqlErrors: [],
    toasts: [],
  };
  window.__QA_TELEMETRY__ = telemetry;

  function pushBounded(arr, item) {
    arr.push(item);
    if (arr.length > MAX_EVENTS) {
      arr.splice(0, arr.length - MAX_EVENTS);
    }
  }

  // 1. Console errors & uncaught runtime errors
  const origConsoleError = console.error;
  console.error = function (...args) {
    try {
      pushBounded(telemetry.consoleErrors, {
        ts: new Date().toISOString(),
        url: redactText(location.href),
        message: args.map(safeFormatArg).join(' ').slice(0, MAX_TEXT),
      });
    } catch (_err) {
      // Never break app console calls
    }
    return origConsoleError.apply(this, args);
  };

  window.addEventListener('error', (event) => {
    pushBounded(telemetry.pageErrors, {
      ts: new Date().toISOString(),
      url: redactText(location.href),
      message: redactText(event.message || 'Script error'),
      source: redactText(event.filename || ''),
      line: event.lineno || 0,
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event && event.reason !== undefined ? safeFormatArg(event.reason) : 'Unhandled rejection';
    pushBounded(telemetry.unhandledRejections, {
      ts: new Date().toISOString(),
      url: redactText(location.href),
      reason,
    });
  });

  // 2. Read-only fetch & XHR observation (status >= 400 + GraphQL HTTP 200 errors)
  function isJsonLikeContentType(ct) {
    const lower = (ct || '').toLowerCase();
    if (lower.includes('text/event-stream')) return false;
    return lower.includes('application/json') || lower.includes('application/graphql') || lower.includes('+json');
  }

  function inspectJsonPayload(url, method, status, payload) {
    if (!payload || typeof payload !== 'object') return;
    if (Array.isArray(payload.errors) && payload.errors.length > 0) {
      pushBounded(telemetry.graphqlErrors, {
        ts: new Date().toISOString(),
        method,
        url: redactText(url),
        status,
        errors: redactJson(payload.errors.slice(0, 5)),
      });
    }
  }

  if (typeof window.fetch === 'function') {
    const origFetch = window.fetch;
    window.fetch = async function (input, init) {
      const reqUrl = typeof input === 'string' ? input : (input && input.url) || '';
      const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      try {
        const res = await origFetch.apply(this, arguments);
        const ct = (res.headers && res.headers.get('content-type')) || '';
        if (res.status >= 400) {
          let excerpt = '';
          if (isJsonLikeContentType(ct) || ct.toLowerCase().startsWith('text/plain')) {
            try {
              const rawText = await res.clone().text();
              excerpt = redactText(rawText);
            } catch (_err) {
              excerpt = '';
            }
          }
          pushBounded(telemetry.networkFailures, {
            ts: new Date().toISOString(),
            transport: 'fetch',
            method,
            url: redactText(reqUrl),
            status: res.status,
            excerpt,
          });
        } else if (res.status === 200 && isJsonLikeContentType(ct)) {
          res.clone().json().then(
            (data) => inspectJsonPayload(reqUrl, method, res.status, data),
            () => {}
          );
        }
        return res;
      } catch (err) {
        pushBounded(telemetry.networkFailures, {
          ts: new Date().toISOString(),
          transport: 'fetch',
          method,
          url: redactText(reqUrl),
          status: 0,
          excerpt: redactText(err && err.message ? err.message : String(err)),
        });
        throw err;
      }
    };
  }

  if (typeof XMLHttpRequest === 'function') {
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      this.__qaMethod = (method || 'GET').toUpperCase();
      this.__qaUrl = url ? String(url) : '';
      return origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
      const xhr = this;
      if (!xhr.__qaHooked) {
        xhr.__qaHooked = true;
        xhr.addEventListener('loadend', () => {
          try {
            const status = xhr.status || 0;
            const ct = xhr.getResponseHeader('content-type') || '';
            const method = xhr.__qaMethod || 'GET';
            const url = xhr.__qaUrl || '';
            const canReadText = !xhr.responseType || xhr.responseType === 'text';
            if (status === 0 || status >= 400) {
              pushBounded(telemetry.networkFailures, {
                ts: new Date().toISOString(),
                transport: 'xhr',
                method,
                url: redactText(url),
                status,
                excerpt: canReadText ? redactText(xhr.responseText || '') : '',
              });
            } else if (status === 200 && canReadText && isJsonLikeContentType(ct) && xhr.responseText) {
              try {
                inspectJsonPayload(url, method, status, JSON.parse(xhr.responseText));
              } catch (_err) {
                // Ignore non-JSON body
              }
            }
          } catch (_err) {
            // Never interfere with app XHR handlers
          }
        });
      }
      return origSend.apply(this, arguments);
    };
  }

  // 3. Ephemeral toast / alert / snackbar MutationObserver
  function recordToastNode(node) {
    if (!node || node.nodeType !== 1) return;
    const role = (node.getAttribute && node.getAttribute('role')) || '';
    const cls = typeof node.className === 'string' ? node.className : '';
    const text = (node.innerText || node.textContent || '').trim();
    if (!text) return;
    if (role === 'alert' || role === 'status' || /(toast|snack|alert|notif|flash)/i.test(cls)) {
      pushBounded(telemetry.toasts, {
        ts: new Date().toISOString(),
        role,
        className: cls.slice(0, 80),
        text: redactText(text),
      });
    }
  }

  function startToastObserver() {
    if (!document.body || window.__qaToastObs) return;
    const obs = new MutationObserver((mutations) => {
      for (const mut of mutations) {
        for (const node of mut.addedNodes) {
          recordToastNode(node);
          if (node && node.querySelectorAll) {
            const nested = node.querySelectorAll('[role="alert"], [role="status"]');
            for (const el of nested) recordToastNode(el);
          }
        }
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    window.__qaToastObs = obs;
  }

  if (document.body) {
    startToastObserver();
  } else {
    document.addEventListener('DOMContentLoaded', startToastObserver, { once: true });
  }

  // 4. Drain buffered telemetry per step/case
  window.__QA_DRAIN__ = function () {
    const snapshot = {
      url: redactText(location.href),
      consoleErrors: telemetry.consoleErrors.splice(0),
      pageErrors: telemetry.pageErrors.splice(0),
      unhandledRejections: telemetry.unhandledRejections.splice(0),
      networkFailures: telemetry.networkFailures.splice(0),
      graphqlErrors: telemetry.graphqlErrors.splice(0),
      toasts: telemetry.toasts.splice(0),
    };
    return snapshot;
  };

  // 5. Active DOM, layout & WCAG 2.2 AA audit helper
  function isVisible(el) {
    if (!el || el.offsetParent === null) {
      const style = el ? getComputedStyle(el) : null;
      if (!style || style.position !== 'fixed' || style.display === 'none' || style.visibility === 'hidden') {
        return false;
      }
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function hasAccessibleName(el) {
    const ariaLabel = (el.getAttribute('aria-label') || '').trim();
    const ariaLabelledBy = (el.getAttribute('aria-labelledby') || '').trim();
    const title = (el.getAttribute('title') || '').trim();
    if (ariaLabel || ariaLabelledBy || title) return true;
    const id = el.id;
    if (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) return true;
    if (el.closest('label')) return true;
    const tag = el.tagName.toLowerCase();
    if (tag === 'button' || tag === 'a' || el.getAttribute('role') === 'button') {
      const text = (el.innerText || el.textContent || '').trim();
      const imgAlt = el.querySelector('img[alt]:not([alt=""])');
      return Boolean(text || imgAlt);
    }
    return false;
  }

  window.__QA_AUDIT__ = function () {
    const brokenImages = [...document.images]
      .filter((img) => img.complete && img.naturalWidth === 0)
      .map((img) => redactText(img.getAttribute('src') || img.alt || '(unnamed)'));

    const docEl = document.documentElement;
    const overflowX = docEl.scrollWidth > window.innerWidth;

    const unlabeledInputs = [];
    const unlabeledClickables = [];
    const smallTargets = [];
    const obscuredOrClipped = [];

    for (const el of document.querySelectorAll('input, select, textarea')) {
      if (el.type === 'hidden' || el.disabled || !isVisible(el)) continue;
      if (!hasAccessibleName(el)) {
        unlabeledInputs.push(el.name || el.id || el.type || el.tagName.toLowerCase());
      }
    }

    const interactiveSel = 'a[href], button, [role="button"], input:not([type="hidden"]), select, textarea';
    for (const el of document.querySelectorAll(interactiveSel)) {
      if (el.disabled || !isVisible(el)) continue;
      const rect = el.getBoundingClientRect();
      const tag = el.tagName.toLowerCase();
      const label = (el.innerText || el.getAttribute('aria-label') || el.name || el.id || tag).trim().slice(0, 60);

      if ((tag === 'button' || tag === 'a' || el.getAttribute('role') === 'button') && !hasAccessibleName(el)) {
        unlabeledClickables.push(el.id || el.className || tag);
      }
      const inProse = tag === 'a' && Boolean(el.closest('p, li, td, th, dd, dt, blockquote, figcaption'));
      const isInlineLink = inProse && getComputedStyle(el).display === 'inline';
      if (!isInlineLink && (rect.width < 24 || rect.height < 24)) {
        smallTargets.push({ label, width: Math.round(rect.width), height: Math.round(rect.height) });
      }
      if (rect.right > window.innerWidth + 1 || rect.left < -1) {
        obscuredOrClipped.push({ issue: 'offscreen_x', label, left: Math.round(rect.left), right: Math.round(rect.right) });
      } else if (rect.top >= 0 && rect.bottom <= window.innerHeight) {
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const hit = document.elementFromPoint(cx, cy);
        const ownLabel = el.closest('label');
        const hitInOwnLabel = Boolean(ownLabel && hit && (hit === ownLabel || ownLabel.contains(hit)));
        if (hit && hit !== el && !el.contains(hit) && !hit.contains(el) && !hitInOwnLabel) {
          obscuredOrClipped.push({
            issue: 'obscured_by_overlay',
            label,
            coveredBy: (hit.id || hit.className || hit.tagName).toString().slice(0, 60),
          });
        }
      }
    }

    const idCounts = Object.create(null);
    for (const el of document.querySelectorAll('[id]')) {
      if (el.id) idCounts[el.id] = (idCounts[el.id] || 0) + 1;
    }
    const duplicateIds = Object.keys(idCounts).filter((k) => idCounts[k] > 1).slice(0, 20);

    let focusedObscured = null;
    const active = document.activeElement;
    if (active && active !== document.body && active !== document.documentElement && isVisible(active)) {
      const aRect = active.getBoundingClientRect();
      if (aRect.top >= 0 && aRect.bottom <= window.innerHeight && aRect.left >= 0 && aRect.right <= window.innerWidth) {
        const hit = document.elementFromPoint(aRect.left + aRect.width / 2, aRect.top + aRect.height / 2);
        if (hit && hit !== active && !active.contains(hit) && !hit.contains(active)) {
          focusedObscured = {
            tag: active.tagName.toLowerCase(),
            label: (active.innerText || active.getAttribute('aria-label') || active.name || active.id || active.tagName).trim().slice(0, 60),
            coveredBy: (hit.id || hit.className || hit.tagName).toString().slice(0, 60),
          };
        }
      }
    }

    return {
      url: redactText(location.href),
      viewport: { width: window.innerWidth, height: window.innerHeight, scrollWidth: docEl.scrollWidth },
      overflowX,
      brokenImages,
      unlabeledInputs: unlabeledInputs.slice(0, 25),
      unlabeledClickables: unlabeledClickables.slice(0, 25),
      smallTargets: smallTargets.slice(0, 25),
      obscuredOrClipped: obscuredOrClipped.slice(0, 25),
      duplicateIds,
      focusedObscured,
    };
  };

  return telemetry;
})();
