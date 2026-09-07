# GUI Platform Operations Runbook — Phase 18

## Local development

```bash
cd frontend-web
npm install
npm run dev
```

Vite binds to `0.0.0.0:4173`. The development proxy forwards `/api` and `/ws`
to `127.0.0.1:8000`; browser code uses relative URLs and never calls
`localhost` directly. In Agent Mode this is compatible with the proxied live
preview host.

## Environment

Copy `.env.example` to `.env.local`:

```dotenv
VITE_API_BASE_URL=
VITE_API_VERSION=v1
VITE_DEMO_MODE=true
VITE_REALTIME_ENABLED=false
VITE_APP_NAME=Tekarai
```

- Keep `VITE_DEMO_MODE=true` for a local UI review without the backend.
- Set it to `false` in an authenticated deployment.
- Never put provider keys, API secrets, passwords or long-lived credentials in
  Vite variables. Values prefixed with `VITE_` are public browser configuration.
- If the API is same-origin, leave `VITE_API_BASE_URL` empty.

## Quality gate

```bash
npm run typecheck
npm test
npm run build
npm run test:e2e
```

The release gate expects TypeScript project build, unit/component/integration
contract tests, a production Vite build and Chromium desktop/mobile smoke
journeys. `npm run test:coverage` is available for CI coverage collection.

## Deployment

1. Run the quality gate from a clean checkout.
2. Set `VITE_DEMO_MODE=false` and the versioned API configuration at build
   time.
3. Serve `dist/` from a same-origin HTTPS host or configure a strict API CORS
   allowlist. Do not use `*` with credentials.
4. Configure the web server to serve `index.html` for `/login` and `/app/*`
   history-fallback routes.
5. Forward `/api/` to the backend and `/ws/` to the ASGI WebSocket endpoint.
6. Use secure, same-site session/cookie infrastructure for production token
   handling. The sessionStorage demo adapter is not a production identity
   provider.
7. Keep source maps access-controlled if they contain internal source paths.

## Operational behavior

- GET requests have a bounded timeout and retry only transient failures.
- Mutations are not automatically retried; callers can supply idempotency keys
  to the backend contract.
- The application shell preserves the current UI state on network failure and
  displays a retryable error state.
- Tenant-aware server cache keys include tenant, resource and parameters;
  invalidation is explicit and cache data is never treated as source of truth.
- WebSocket reconnection uses bounded exponential backoff and is disabled until
  `VITE_REALTIME_ENABLED=true`.
- Telemetry never emits raw auth tokens, passwords, secrets or cookies. Use the
  browser `tekarai:telemetry` event to bridge approved events to an observability
  provider.

## Security review checklist

- [ ] Demo mode disabled in production.
- [ ] API and WebSocket served over HTTPS/WSS.
- [ ] Backend authentication, tenant isolation and permissions enabled.
- [ ] CSP, frame-ancestors and secure headers configured at the web server.
- [ ] No secrets in built assets or environment variables.
- [ ] File upload MIME/extension/size/malware rules enforced by the backend.
- [ ] CORS and CSRF policy reviewed with the backend deployment.
- [ ] Audit events available for sensitive changes.
- [ ] Error responses do not expose stack traces or database details.
- [ ] Keyboard, screen-reader, contrast and RTL smoke review complete.

## Incident playbook

### API unavailable

The shell shows a connection error and preserves the current view. Verify
backend readiness, reverse-proxy routing and `VITE_API_BASE_URL`; retry from
the view. Do not enable demo mode as a production incident workaround.

### Repeated 401 responses

Confirm clock/session expiry, refresh endpoint routing and cookie/token policy.
The client makes one serialized refresh attempt and then clears the session.
Inspect correlation IDs, not token values.

### Wrong tenant data

Stop the deployment, verify backend scope enforcement and audit events, and
invalidate application caches. The frontend tenant selector is not a security
boundary.

### Broken route after deployment

Verify history fallback routes to `index.html`, then verify the API proxy keeps
`/api/v1/` intact. Do not add unversioned endpoint strings to components.
