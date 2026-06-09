# Lab 03 — CSRF Protection

## Learning goals

By the end of this lab you will be able to:

- Explain what a CSRF attack is and why it works.
- Describe the double submit cookie pattern and how it defeats CSRF.
- Explain why `SameSite=Strict` alone is not sufficient protection.
- Trace the full CSRF token lifecycle in this application — from issuance to validation.
- Identify what makes an endpoint CSRF-safe vs CSRF-vulnerable.
- Explain why `permitAll()` does not bypass CSRF protection.
- Demonstrate a CSRF attack against an unprotected endpoint.
- Verify that the application correctly rejects requests with a missing or wrong token.

---

## Background

### What is CSRF?

A Cross-Site Request Forgery (CSRF) attack tricks a user's browser into sending a request to your application from a different website — using the user's existing session.

The attack works because browsers automatically attach cookies to every request for a domain, regardless of which site triggered the request.

**Example attack scenario:**

1. Alice is logged in to `securetask.example.com`. Her browser holds a valid `BFF-SESSION` cookie (the BFF's session cookie).
2. Alice visits a malicious page at `evil.example.com`.
3. That page contains a hidden HTML form that submits to `https://securetask.example.com/api/admin/users/2/role`.
4. The form submission fires automatically on page load.
5. Alice's browser attaches her `BFF-SESSION` cookie to the request.
6. The BFF sees an authenticated request and — without CSRF protection — proxies it to the main API.

Alice just changed someone's role without knowing it.

### Why cookies alone are not enough

The browser's cookie policy sends cookies automatically. Authentication based purely on session cookies is vulnerable because the server cannot tell whether a request came from the legitimate application or from an attacker-controlled page.

### The double submit cookie pattern

The fix is to require a secret value that:
- The server generates and sends as a cookie
- The legitimate JavaScript client can read from that cookie and echo back as a request header
- An attacker-controlled page cannot read (same-origin policy prevents cross-origin cookie reads)

This secret is the **CSRF token**. On every state-changing request, the client must submit the token value in a custom header (`X-XSRF-TOKEN`). The server compares the header value against the cookie value. If they don't match, the request is rejected.

The key distinction from the **synchronizer token pattern**: the server does not store the token server-side. The cookie is both the storage and the ground truth. The validation is purely: does the value in the cookie match the value in the header? An attacker cannot win because they can force the browser to send the cookie, but cannot read it to forge the header.

### Why SameSite=Strict is not sufficient alone

`SameSite=Strict` tells the browser not to send cookies on cross-site requests. This defeats most CSRF attacks in modern browsers. However:

- Older browsers do not support `SameSite`.
- Some browser extensions can bypass it.
- Subdomain attacks (`evil.securetask.example.com`) are still cross-site but share the domain.
- Defence-in-depth requires both: `SameSite=Strict` + the double submit cookie token.

---

## How CSRF protection works in this application

CSRF protection in the browser context is handled by the **BFF** (Backend For Frontend, port 8081). Browser clients never communicate with the main API (port 8080) directly — all browser traffic goes through the BFF, and the BFF enforces CSRF validation before proxying any state-changing request.

### Token issuance

`bff/src/main/java/com/securetask/bff/config/SecurityConfig.java` configures a `CookieCsrfTokenRepository`:

```java
CookieCsrfTokenRepository csrfRepo = CookieCsrfTokenRepository.withHttpOnlyFalse();
```

- The BFF generates a random token and writes it into a cookie named `XSRF-TOKEN`.
- The cookie is the only storage — there is no server-side copy. This is what makes it the double submit cookie pattern, not the synchronizer token pattern.
- `withHttpOnlyFalse()` is deliberate — the JavaScript client must be able to read this cookie.
  The BFF session cookie (`BFF-SESSION`) remains `HttpOnly=true`, so XSS cannot steal the session.

### Forcing the cookie to be written on GET responses

Spring Security 6 uses **deferred CSRF token loading** — the token is only generated and the cookie written when something reads it. Without intervention, a page that only makes GET requests would never receive the cookie, and the first state-changing request after that page load would fail.

`bff/src/main/java/com/securetask/bff/security/CsrfCookieFilter.java` solves this:

```java
CsrfToken csrfToken = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
if (csrfToken != null) {
    csrfToken.getToken(); // Forces lazy loading → cookie is written in the response
}
```

This filter runs on every request to the BFF. The `XSRF-TOKEN` cookie is therefore always fresh.

### Token submission

`frontend/js/api.js` reads the cookie and sends it as a custom request header on every state-changing request:

```javascript
function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)XSRF-TOKEN=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : null;
}

// In apiRequest():
const token = getCsrfToken();
if (token) {
    headers["X-XSRF-TOKEN"] = token;
}
```

Custom headers (`X-XSRF-TOKEN`) cannot be set by a cross-origin HTML form. Only JavaScript running on the same origin can set them. This is why the double submit cookie pattern works.

### Token validation

The BFF's `CsrfFilter` intercepts every `POST`, `PATCH`, `PUT`, and `DELETE` request sent to the BFF. It reads the `XSRF-TOKEN` cookie value from the incoming request and compares it against the `X-XSRF-TOKEN` header (or `_csrf` form parameter). If they do not match, the request is rejected with `403 Forbidden` — the main API is never reached. No server-side token lookup is needed.

### Login and logout

Login (`/login`) uses `application/x-www-form-urlencoded`. The `api.js` login function appends `_csrf` as a form parameter:

```javascript
params.append("_csrf", token);
```

The BFF's `SessionController` validates the `_csrf` parameter and, on success, calls the main API's `POST /api/auth/token` to obtain a JWT, which the BFF then stores server-side and uses for subsequent proxied requests.

Logout (`/logout`) is called via `apiRequest("POST", "/logout")`, which attaches `X-XSRF-TOKEN` automatically.

### Why `permitAll()` does not bypass CSRF

A common misconception: listing an endpoint in `permitAll()` inside `authorizeHttpRequests` only removes the **authentication** requirement. The CSRF filter runs earlier in the filter chain — before authorization is evaluated. CSRF is checked on every state-changing request, including the public `/api/register` endpoint. The only exceptions are the stateless JWT token endpoints (`/api/auth/token`, `/api/auth/refresh`, `/api/auth/revoke`), which are explicitly exempt via `csrf().ignoringRequestMatchers(...)`. Those endpoints use `Authorization: Bearer` headers — they do not rely on session cookies, so a cross-origin form cannot trigger them with a victim's credentials. CSRF protection only applies to session-based authentication.

---

## Relevant files

| File | Purpose |
|------|---------|
| `bff/src/main/java/com/securetask/bff/config/SecurityConfig.java` | BFF CSRF configuration — repository, handler, filter |
| `bff/src/main/java/com/securetask/bff/security/CsrfCookieFilter.java` | Forces the XSRF-TOKEN cookie to be written on every BFF response |
| `frontend/js/api.js` | `getCsrfToken()` + `X-XSRF-TOKEN` header on all state-changing requests |
| `bff/src/main/resources/application.properties` | `SameSite=Strict` and `HttpOnly=true` on the BFF session cookie |

---

## Step-by-step guide

### Step 1 — Observe the token in your browser

Start the application (`./gradlew :bff:bootRun` and `./gradlew :api:bootRun`) and open the browser developer tools.

1. Navigate to http://localhost:8081/login.html
2. Open the **Application** tab → **Cookies** → `localhost`
3. Find the `XSRF-TOKEN` cookie (the BFF's CSRF token). Note:
   - `HttpOnly` is **false** — JavaScript can read it
   - `SameSite` is blank (the CSRF token cookie) — the session cookie has `Strict`
4. Find the `BFF-SESSION` cookie (the BFF's session cookie). Note:
   - `HttpOnly` is **true** — JavaScript cannot read it

**Question:** Why must `XSRF-TOKEN` have `HttpOnly=false` while `BFF-SESSION` has `HttpOnly=true`?

### Step 2 — Watch the token flow through a login

Open the **Network** tab. Log in with your credentials at http://localhost:8081/login.html.

Find the `POST /login` request. In the **Payload** section you will see:
```
username=alice&password=...&_csrf=<token>
```

The CSRF token is sent as a form parameter. The BFF's `SessionController` reads it from `_csrf`, validates it against the BFF session, and then calls the main API's `POST /api/auth/token` to complete authentication.

### Step 3 — Watch the token flow through a state-changing API call

Still in the Network tab, go to the admin panel at http://localhost:8081 and change a user's role.

Find the `PATCH /api/admin/users/{id}/role` request. In the **Request Headers** section you will see:
```
X-XSRF-TOKEN: <token>
```

This header cannot be set by a cross-origin form. Only same-origin JavaScript can set custom headers. The BFF validates the header before proxying the request to the main API with a JWT Bearer token injected on behalf of the logged-in user.

### Step 4 — Find a target user ID

You need the ID of a **different** user to change their role (the API blocks an admin from changing their own role). Fetch the user list first:

```javascript
fetch("/api/admin/users", { credentials: "include" })
  .then(r => r.json()).then(console.log);
```

Find the `id` of a VIEWER user. Use that ID in place of `<VIEWER_ID>` in the steps below.

### Step 5 — Demonstrate a rejected request (missing token)

Open a browser console on http://localhost:8081 (same origin) and run:

```javascript
// Send a PATCH with no CSRF token
fetch("/api/admin/users/<VIEWER_ID>/role", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ role: "VIEWER" })
}).then(r => console.log("Status:", r.status));
```

Expected output: `Status: 403`

The BFF rejected the request because `X-XSRF-TOKEN` was absent. The main API was never reached.

### Step 6 — Demonstrate a rejected request (wrong token)

```javascript
fetch("/api/admin/users/<VIEWER_ID>/role", {
    method: "PATCH",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": "invalid-token"
    },
    credentials: "include",
    body: JSON.stringify({ role: "VIEWER" })
}).then(r => console.log("Status:", r.status));
```

Expected output: `Status: 403`

### Step 7 — Demonstrate a successful request (correct token)

```javascript
// Read the real token from the cookie
const token = document.cookie.match(/XSRF-TOKEN=([^;]+)/)[1];

fetch("/api/admin/users/<VIEWER_ID>/role", {
    method: "PATCH",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": decodeURIComponent(token)
    },
    credentials: "include",
    body: JSON.stringify({ role: "VIEWER" })
}).then(r => console.log("Status:", r.status));
```

Expected output: `Status: 200`

**Question:** An attacker on `evil.example.com` cannot execute Step 7 successfully. Why not?

### Step 8 — Simulate the CSRF attack (same-origin demonstration)

This demonstrates what an attacker *would* try. Because you are on the same origin, you can show that the token is what prevents it — not the origin check.

Open a console on http://localhost:8081 and try submitting a form-encoded request without the token (as a cross-origin form would):

```javascript
const body = new URLSearchParams({ role: "VIEWER" });
fetch("/api/admin/users/<VIEWER_ID>/role", {
    method: "PATCH",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    credentials: "include",
    body: body.toString()
}).then(r => console.log("Status:", r.status));
```

Expected output: `Status: 403`

The request was rejected by the BFF because it did not include the `X-XSRF-TOKEN` header or `_csrf` parameter — exactly what an HTML form submitted from `evil.example.com` would look like.

### Step 8 — Inspect the filter chain order

Open `bff/src/main/java/com/securetask/bff/config/SecurityConfig.java`. Find:

```java
.addFilterAfter(new CsrfCookieFilter(), BasicAuthenticationFilter.class)
```

Open `bff/src/main/java/com/securetask/bff/security/CsrfCookieFilter.java`. Notice that `getToken()` is the only call — it forces the lazy token to resolve, which causes `CookieCsrfTokenRepository` to write the `XSRF-TOKEN` cookie into the BFF response.

**Question:** What would happen on the first Save button click in the admin panel if `CsrfCookieFilter` were removed?

---

## Investigating the Double Submit Cookie pattern in Spring Security source

The steps above show the behaviour from the outside (browser DevTools). This section shows how to trace the same flow through the Spring Security source code so you understand exactly what the framework is checking.

### How to get the sources

The sources jar is already in your Gradle cache after the first build:

```
~/.gradle/caches/modules-2/files-2.1/org.springframework.security/
  spring-security-web/<version>/<hash>/spring-security-web-<version>-sources.jar
```

You can extract the two relevant files to read them:

```bash
jar xf spring-security-web-<version>-sources.jar \
  org/springframework/security/web/csrf/CookieCsrfTokenRepository.java \
  org/springframework/security/web/csrf/CsrfFilter.java
```

### Trace 1 — How the token is stored (cookie write)

Open `CookieCsrfTokenRepository.java` and find `saveToken()`:

```java
ResponseCookie.ResponseCookieBuilder cookieBuilder =
    ResponseCookie.from(this.cookieName, tokenValue)   // cookieName = "XSRF-TOKEN"
        .secure(...)
        .httpOnly(this.cookieHttpOnly)                  // false → JS can read it
        ...
response.addCookie(mapToCookie(cookieBuilder.build()));
```

This is what writes the `XSRF-TOKEN` cookie into the HTTP response. It runs whenever the BFF issues or refreshes a token.

### Trace 2 — How the expected token is loaded (cookie read)

Find `loadToken()` in the same file:

```java
Cookie cookie = WebUtils.getCookie(request, this.cookieName);  // reads XSRF-TOKEN from the incoming request
String token = cookie.getValue();
return new DefaultCsrfToken(this.headerName, this.parameterName, token);
// headerName     = "X-XSRF-TOKEN"
// parameterName  = "_csrf"
// token          = the value from the cookie
```

The **expected** token is whatever value arrived in the `XSRF-TOKEN` cookie. The server issued that value on a previous response.

### Trace 3 — How the actual token is extracted (header read)

Open `CsrfFilter.java` and find `doFilterInternal()`:

```java
String actualToken = this.requestHandler.resolveCsrfTokenValue(request, csrfToken);
```

`resolveCsrfTokenValue` reads the `X-XSRF-TOKEN` request header (or `_csrf` form parameter). This is the value your JavaScript placed there by calling `getCsrfToken()` and setting the header.

### Trace 4 — The comparison

Immediately below:

```java
if (!equalsConstantTime(csrfToken.getToken(), actualToken)) {
    // → 403 AccessDeniedException
}
```

| Variable | Source | Value |
|---|---|---|
| `csrfToken.getToken()` | `XSRF-TOKEN` cookie on the incoming request | What the server previously issued |
| `actualToken` | `X-XSRF-TOKEN` header on the incoming request | What the JS client sent |

If they match → request passes. If not → 403.

The comparison uses `MessageDigest.isEqual` (constant-time) to prevent timing attacks — an attacker cannot deduce the token by measuring how long the comparison takes.

### Why a cross-origin attacker cannot win

```
XSRF-TOKEN cookie  → sent automatically by the browser (attacker can force this)
X-XSRF-TOKEN header → must be set explicitly by JS (attacker cannot read cross-origin cookies)
```

The attacker can make your browser send the cookie, but cannot read it to forge the header. The two values will never match → always 403.

### One detail to notice

In `CsrfFilter.java` line 90 (Spring 6.3):

```java
private CsrfTokenRequestHandler requestHandler = new XorCsrfTokenRequestAttributeHandler();
```

The **default** handler in Spring is the XOR-masked one. This application overrides it with the plain `CsrfTokenRequestAttributeHandler` in `SecurityConfig`, which sends the raw token in the cookie rather than an XOR-masked version. This works correctly but removes the BREACH mitigation. See the Common Mistakes section in this walkthrough and the note in `SecurityConfig.java`.

---

## Manual test checklist

- [ ] `XSRF-TOKEN` cookie is present after loading any page at http://localhost:8081
- [ ] `XSRF-TOKEN` cookie has `HttpOnly=false`
- [ ] `BFF-SESSION` cookie has `HttpOnly=true` and `SameSite=Strict`
- [ ] `POST /login` payload includes `_csrf` parameter
- [ ] `PATCH /api/admin/users/{id}/role` request includes `X-XSRF-TOKEN` header
- [ ] Request without `X-XSRF-TOKEN` → 403
- [ ] Request with wrong `X-XSRF-TOKEN` value → 403
- [ ] Request with correct `X-XSRF-TOKEN` value → 200

---

## Expected results

| Request | Token | Expected |
|---------|-------|----------|
| `PATCH` with no token | absent | 403 Forbidden |
| `PATCH` with wrong token | `"invalid"` | 403 Forbidden |
| `PATCH` with correct token | from cookie | 200 OK |
| `POST /api/register` with no token | absent | 403 Forbidden (BFF CSRF filter rejects before proxying) |
| `GET /api/me` with no token | N/A (GET is safe) | 200 OK |

---

## Common mistakes

**Mistake:** Disabling CSRF protection globally with `.csrf(csrf -> csrf.disable())`.
**Why it matters:** This removes protection from every endpoint in one line. It is commonly done to "fix" 403 errors during development without understanding the root cause.

**Mistake:** Adding an endpoint to `csrf().ignoringRequestMatchers(...)` to avoid token errors.
**Why it matters:** It makes that endpoint vulnerable to CSRF regardless of other protections.

**Mistake:** Setting `XSRF-TOKEN` to `HttpOnly=true`.
**Why it matters:** JavaScript cannot read an `HttpOnly` cookie. The client has no token to send, and every state-changing request will fail with 403.

**Mistake:** Relying on `SameSite=Strict` alone and disabling the token.
**Why it matters:** `SameSite` is a browser feature. Older browsers, misconfigured proxies, and certain attack vectors (e.g. subdomain takeover) can bypass it. The double submit cookie pattern works independently of browser behavior.

**Mistake:** Believing `permitAll()` disables CSRF for that endpoint.
**Why it matters:** `permitAll()` is an authorization rule — it only removes the authentication requirement. The `CsrfFilter` runs before authorization and is unaffected.

**Mistake:** Using `CsrfTokenRequestAttributeHandler` instead of `XorCsrfTokenRequestAttributeHandler`.
**Why it matters:** The plain handler puts the raw token value in the cookie on every response. If the token is reflected anywhere in a gzip-compressed HTTPS response, an attacker who can make many requests from the victim's browser can measure response sizes and recover the token one character at a time (BREACH attack). The XOR handler masks the token with a fresh random value on every response, so the compressed output is different each time and the size comparison yields no signal. The fix is a one-word change in `SecurityConfig`. This application currently uses the plain handler — see the note in `bff/src/main/java/com/securetask/bff/config/SecurityConfig.java`.

---

## Discussions

**Q1: What is a CSRF attack? Describe the sequence of events from the attacker's perspective.**

1. The attacker identifies a state-changing request the victim's application accepts — for example, `PATCH /api/admin/users/2/role` to change a user's role.
2. The attacker hosts a page at `evil.example.com` containing a hidden form or JavaScript that sends that request.
3. The attacker tricks the victim (a logged-in admin) into visiting `evil.example.com`.
4. The browser automatically attaches the victim's `BFF-SESSION` cookie to the request, because cookies are sent based on the destination domain, not the origin of the request.
5. The BFF receives an authenticated-looking request and — without CSRF protection — would proxy it to the main API.

The attacker never sees the response. They do not need to. The goal is to trigger the action, not to read the result.

**Q2: Why can an attacker's HTML form submit a request with the victim's session cookie, but not include the correct `X-XSRF-TOKEN` header?**

**Cookies** are attached by the browser automatically, controlled by the browser's cookie policy, not by the page's code. Any page can trigger a request that carries the target domain's cookies — this is by design for legitimate cross-site navigation.

**Custom headers** (`X-XSRF-TOKEN`) can only be set by JavaScript, and the browser's same-origin policy prevents cross-origin JavaScript from reading cookies on a different domain. An attacker on `evil.example.com` cannot call `document.cookie` and see `XSRF-TOKEN` from `securetask.example.com`. Without the token value, they cannot set the header.

HTML forms also cannot set arbitrary headers — only standard fields like `Content-Type` in a limited set. So a cross-origin form submission will never include `X-XSRF-TOKEN`.

**Q3: What is the double submit cookie pattern? How does it defeat CSRF? How does it differ from the synchronizer token pattern?**

The server generates a random, unpredictable token and writes it into a readable cookie (`XSRF-TOKEN`). On every state-changing request, the JavaScript client reads the cookie and echoes the value back as a custom header (`X-XSRF-TOKEN`). The server compares the cookie value against the header value — if they match, the request is allowed.

An attacker cannot forge this because:
- They cannot read the `XSRF-TOKEN` cookie from the victim's browser (same-origin policy).
- They cannot set the `X-XSRF-TOKEN` header from a cross-origin context.

The token acts as proof that the request was initiated by code running on the legitimate page.

**Difference from the synchronizer token pattern:** In the synchronizer token pattern the server stores the token server-side (in the session or database) and compares the submitted value against that stored copy. In the double submit cookie pattern there is no server-side storage — the cookie is both the storage and the reference value. The server only compares two things that arrived in the same request: the cookie and the header.

**Q4: Why does `SameSite=Strict` on the session cookie not make the double submit cookie token redundant?**

`SameSite=Strict` instructs the browser to not send the session cookie on any cross-site request. This defeats the standard CSRF attack. However:

- **Browser support:** Older browsers and some non-browser HTTP clients ignore `SameSite`. A user on an outdated browser is unprotected.
- **Subdomain attacks:** If an attacker controls a subdomain (e.g. via a subdomain takeover or XSS on a sibling subdomain), the same-site boundary may not apply depending on the browser's definition.
- **It is a browser-level control, not a server-level control.** The server has no way to verify that the browser enforced it. The double submit cookie token is a server-enforced check — it works regardless of browser behavior.

Defence-in-depth: both protections together provide redundancy when either one fails.

**Q5: Explain the purpose of `CsrfCookieFilter`. What bug would occur without it?**

Spring Security 6 uses deferred CSRF token loading. The token is generated lazily — the `XSRF-TOKEN` cookie is only written into the response when something explicitly reads the token object. For `GET` requests (which don't need CSRF validation), the token is never read, so the cookie is never set or refreshed.

Without `CsrfCookieFilter`, the `XSRF-TOKEN` cookie would not be present when a user first loads the admin panel (which starts with a `GET /api/admin/users`). The first `PATCH` request would have no token to send and would fail with 403. The second click would work because the 403 response itself triggered the cookie to be written.

`CsrfCookieFilter` calls `csrfToken.getToken()` on every request to the BFF, which forces the lazy resolution and ensures the cookie is always written in the response — so the first state-changing request always has a valid token available.

**Q6: Why is `XSRF-TOKEN` set to `HttpOnly=false` while `BFF-SESSION` is `HttpOnly=true`?**

`HttpOnly=true` prevents JavaScript from reading the cookie. This is the right setting for the BFF session cookie — XSS code on the page should not be able to steal the session identifier.

But the CSRF token needs to be read by JavaScript so it can be included in the `X-XSRF-TOKEN` header. If `XSRF-TOKEN` were `HttpOnly=true`, `getCsrfToken()` in `api.js` would always return `null`, and every state-changing request would fail with 403.

The XSRF-TOKEN cookie being readable by JavaScript is not a security problem because:
- Its only purpose is to be read and echoed back in a header.
- An attacker on another origin still cannot read it — the same-origin policy prevents cross-origin JavaScript from accessing another domain's cookies, regardless of the `HttpOnly` flag.
- XSS can read it, but XSS can also make requests directly without needing the CSRF token — so losing the CSRF token to XSS does not add meaningful new capability to the attacker.

**Q7: Does listing `/api/register` in `permitAll()` bypass CSRF protection? Why or why not?**

No. `permitAll()` is part of the **authorization** filter — it determines whether an authenticated session is required. The **CSRF filter** (`CsrfFilter`) runs earlier in the filter chain, before authorization is evaluated.

In Spring Security, the only way to exempt a path from CSRF is to call `csrf().ignoringRequestMatchers(...)` explicitly. This application uses that exemption only for the stateless JWT token endpoints (`/api/auth/token`, `/api/auth/refresh`, `/api/auth/revoke`) — those endpoints use `Authorization: Bearer` headers and are not vulnerable to cookie-based CSRF. Every other path, including `/api/register`, is protected.

As a result, `POST /api/register` still requires a valid `X-XSRF-TOKEN` header (or `_csrf` form parameter). The `api.js` registration function correctly includes it via `apiRequest()`. A cross-origin form submission to `/api/register` would fail with 403 because the attacker cannot read the `XSRF-TOKEN` cookie to include it.
