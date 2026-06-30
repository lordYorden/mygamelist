# Lab 04 — SSRF Prevention

## Learning goals

By the end of this lab you should be able to:

1. Explain what Server-Side Request Forgery (SSRF) is and why it matters.
2. Identify code that makes outbound HTTP requests to user-supplied URLs without validation.
3. Describe what an attacker can reach on a typical cloud deployment (internal services, metadata API).
4. Explain why filtering the URL string alone is not enough — DNS must be resolved at validation time.
5. Describe the four-layer defence in `SsrfGuard`: HTTPS-only, domain allowlist, IP range check, no redirects.
6. Trace the request flow through `WebhookController → WebhookService → SsrfGuard`.
7. Articulate what the current fix does *not* protect against (DNS rebinding).
8. Recognize common application features that introduce SSRF (webhooks, upload-from-URL, PDF generation, OAuth flows, LLM tool calls).
9. List additional hardening steps beyond the application layer: response size limits, Content-Type validation, and network-level egress controls.

---

## Background

### What is SSRF?

In a Server-Side Request Forgery attack the attacker tricks the server into making an HTTP request on their behalf. The request appears to originate from the server itself, bypassing any firewalls or security groups that restrict where the *attacker* can connect from.

A typical scenario in a task-management app: a user registers a webhook URL. Later, the app calls that URL to deliver an event notification. If the app calls the URL without validation, an attacker can register `https://169.254.169.254/latest/meta-data/iam/security-credentials/` — the AWS instance metadata endpoint — and the server will hand back the EC2 instance's IAM credentials in the webhook test response. From there the attacker has AWS API access.

### What else can SSRF reach?

- **Internal services**: databases, caches, admin UIs, Kubernetes API servers — anything the app server can reach on the internal network but the attacker cannot reach from the outside.
- **Cloud metadata APIs**: AWS (`169.254.169.254`), GCP (`169.254.169.254`), Azure (`169.254.169.254`) — all share the same link-local IP and expose IAM credentials, user-data scripts, and configuration.
- **Localhost services**: the app itself (think: an unexposed actuator endpoint at `/actuator/env`), or any service bound to `127.0.0.1`.
- **Port scanning**: by varying the port and observing response times or error messages an attacker can enumerate open ports on internal hosts.

OWASP ranks this as **A10:2021 — Server-Side Request Forgery**.

### Why string filtering is not enough

A naive guard might check:

```java
if (url.startsWith("https://127.0.0.1") || url.startsWith("https://localhost")) {
    throw new BlockedUrlException(...);
}
```

This fails in multiple ways:

- `https://127.1/` resolves to `127.0.0.1` on most systems.
- `https://0x7f000001/` is hex notation for `127.0.0.1`.
- `https://internal-service.corp/` resolves to a private IP — you checked the string, not the address.
- IPv6 bypasses all IPv4 checks: `https://[::1]/`.

The only reliable approach: **resolve the hostname to an IP address, then check the IP against known-internal ranges.** Combine this with a domain allowlist so unknown external targets are also rejected.

### Where SSRF hides in real applications

SSRF does not only appear in webhooks. It surfaces in any feature where user input decides where the server connects:

| Feature | SSRF vector |
|---------|-------------|
| "Upload image from URL" | URL supplied by the user |
| Webhook notifications | Callback URL stored by the user |
| PDF / thumbnail generation | URL embedded in user-supplied content |
| URL preview / link unfurling | URL shared by the user |
| OAuth / SSO integrations | The `redirect_uri` or provider discovery URL |
| LLM tools that fetch URLs | Any URL the model extracts from user input |

**Rule of thumb:** If user input affects *where* the server connects, SSRF is possible.

### Synchronizer token pattern for webhooks

This lab uses the synchronizer token pattern established in Lab 03 for state-changing requests (`POST`, `DELETE`). The CSRF token is still required for all mutating webhook endpoints.

### Developer mental model

Ask this question during design and code review:

> **"Can user input influence where my server connects?"**

If the answer is yes: assume SSRF is possible, require an allowlist, and apply layered defences.

---

## Relevant files

| File | Role |
|------|------|
| `api/src/main/java/com/securetask/entity/Webhook.java` | JPA entity: id, user (FK), url, createdAt |
| `api/src/main/java/com/securetask/repository/WebhookRepository.java` | `findByUser`, `findByIdAndUser` |
| `api/src/main/java/com/securetask/dto/WebhookRequest.java` | Request body for webhook registration — url only |
| `api/src/main/java/com/securetask/dto/WebhookResponse.java` | Safe response — no internal fields |
| `api/src/main/java/com/securetask/dto/WebhookTestResult.java` | Response from the test endpoint: targetStatus, message |
| `api/src/main/java/com/securetask/service/SsrfGuard.java` | Four-layer validation before any outbound request |
| `api/src/main/java/com/securetask/service/BlockedUrlException.java` | Thrown when a URL is blocked — maps to 422 |
| `api/src/main/java/com/securetask/service/OutboundHttpClient.java` | Functional interface wrapping the HTTP call — mockable in tests |
| `api/src/main/java/com/securetask/service/WebhookService.java` | Business logic; calls `ssrfGuard.validate()` before firing |
| `api/src/main/java/com/securetask/controller/WebhookController.java` | REST endpoints; maps `BlockedUrlException` → 422 |
| `api/src/main/java/com/securetask/config/HttpClientConfig.java` | `@Bean OutboundHttpClient` — no redirects, connect/read timeouts |
| `api/src/main/resources/application.properties` | `ssrf.allowed-domains` — the configurable allowlist |
| `api/src/test/java/com/securetask/SsrfGuardTest.java` | Unit tests for each blocked/allowed case |
| `api/src/test/java/com/securetask/WebhookControllerTest.java` | Integration tests with `@MockBean OutboundHttpClient` |

---

## The vulnerable pattern

Without the guard, `WebhookService.testWebhook()` would look like this:

```java
public WebhookTestResult testWebhook(Long id, String callerUsername) {
    User caller = resolveUser(callerUsername);
    Webhook webhook = webhookRepository.findByIdAndUser(id, caller)
            .orElseThrow(() -> new ResourceNotFoundException("Webhook not found"));

    // VULNERABLE — no URL validation before the HTTP call
    int status = outboundHttpClient.post(webhook.getUrl(), Map.of("event", "test"));
    return new WebhookTestResult(status, "Ping delivered");
}
```

An attacker who registered `https://169.254.169.254/latest/meta-data/iam/security-credentials/app-role` and triggered the test endpoint would receive the server's IAM credentials in the response (or in server logs). On a real deployment the response body contains temporary AWS access keys.

---

## How the fix works

`SsrfGuard.validate()` applies four checks in order. All four must pass; any failure throws `BlockedUrlException` and the HTTP call is never made.

### 1 — HTTPS-only scheme check

```java
if (!"https".equalsIgnoreCase(uri.getScheme())) {
    throw new BlockedUrlException("Only https URLs are permitted");
}
```

Rejects `http://`, `file://`, `ftp://`, `gopher://`, and every other scheme. Plain HTTP is disallowed because it carries credentials in the clear and because the TLS handshake provides a basic proof that the target server exists and has a valid certificate — a small but real additional signal.

### 2 — Domain allowlist (primary gate)

```java
if (!isAllowed(host)) {
    throw new BlockedUrlException("Host is not on the webhook allowlist");
}
```

The allowed domains are configured in `api/src/main/resources/application.properties`:

```properties
ssrf.allowed-domains=hooks.slack.com,discord.com,webhook.office.com,hooks.zapier.com,api.pagerduty.com
```

`SsrfGuard` is injected with this list via `@Value("${ssrf.allowed-domains}")`. Matching is **suffix-based**: a configured entry of `discord.com` also allows `webhooks.discord.com`. The check:

```java
private boolean isAllowed(String host) {
    String h = host.toLowerCase();
    for (String domain : allowedDomains) {
        if (h.equals(domain) || h.endsWith("." + domain)) {
            return true;
        }
    }
    return false;
}
```

This is the strongest control: an attacker cannot reach any target — even a legitimately public one — unless it is explicitly listed. Unknown external domains, internal hostnames, and raw IP addresses are all rejected here before DNS is ever consulted.

### 3 — IP range check (defence-in-depth)

```java
InetAddress address = InetAddress.getByName(host);
if (address.isLoopbackAddress()
 || address.isSiteLocalAddress()
 || address.isLinkLocalAddress()
 || address.isAnyLocalAddress()) {
    throw new BlockedUrlException("Requests to internal addresses are not permitted");
}
```

Even if a domain somehow passed the allowlist (e.g. a compromised or misconfigured entry), this check ensures the resolved IP is not internal. `InetAddress.getByName()` normalises IPv6 (`[::1]`) and non-decimal notation (`0177.0.0.1`) before the range check.

| Method | Covers |
|--------|--------|
| `isLoopbackAddress()` | 127.0.0.0/8, ::1 |
| `isSiteLocalAddress()` | 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 |
| `isLinkLocalAddress()` | 169.254.0.0/16 (AWS/GCP/Azure metadata), fe80::/10 |
| `isAnyLocalAddress()` | 0.0.0.0, :: |

### 4 — No redirects + timeouts

```java
// HttpClientConfig — redirect following is explicitly disabled
SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory() {
    @Override
    protected void prepareConnection(HttpURLConnection connection, String httpMethod)
            throws IOException {
        super.prepareConnection(connection, httpMethod);
        connection.setInstanceFollowRedirects(false);   // ← explicit
    }
};
factory.setConnectTimeout(5_000);
factory.setReadTimeout(10_000);
```

**No redirects**: if the target returns a `3xx Location: https://169.254.169.254/`, the client returns that redirect response to the caller rather than following it. Without this, an attacker could register a legitimately allowlisted URL that redirects to an internal address — the guard validates the original URL, but the client follows the redirect and reaches the internal target.

**Timeouts**: without them a slow or non-responsive internal host holds a thread open indefinitely — a resource-exhaustion vector. Five-second connect and ten-second read timeouts bound the worst case.

---

## Step-by-step guide

All steps below reference the current (fixed) codebase.

### Step 1 — Understand the domain model

Open `api/src/main/java/com/securetask/entity/Webhook.java`. The entity has a `ManyToOne` relationship to `User` — each webhook belongs to exactly one user. The `url` field stores the callback URL as registered; no validation happens at save time. The SSRF risk is not in storing the URL — it is in the server calling it.

### Step 2 — Register a webhook with an allowlisted domain

```bash
# Get a token:
TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}' | jq -r .accessToken)

# Register a webhook on an allowlisted domain:
curl -s -X POST http://localhost:8080/api/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://hooks.slack.com/services/T00/B00/xxxx"}'
# → 201 {"id":1,"url":"https://hooks.slack.com/...","userId":1,"createdAt":"..."}
```

Registration accepts any syntactically valid URL. The allowlist is only checked when the webhook is fired.

### Step 3 — Try to register a non-allowlisted domain and fire it

```bash
# (TOKEN obtained in Step 2)

# This registers fine (no validation at save time):
curl -s -X POST http://localhost:8080/api/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://attacker.example.com/collect"}'
# → 201

# Firing it is blocked at the allowlist:
curl -s -X POST http://localhost:8080/api/webhooks/2/test \
  -H "Authorization: Bearer $TOKEN"
# → 422 {"error":"Host is not on the webhook allowlist"}
```

### Step 4 — "Break it": remove the guard and expose the SSRF

Register a webhook pointing at the app's own localhost:

```bash
# (TOKEN obtained in Step 2)

curl -s -X POST http://localhost:8080/api/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://127.0.0.1:8080/actuator/env"}'
# → 201 (stored fine)
```

Now make two temporary edits to expose the vulnerability:

1. In `api/src/main/resources/application.properties`, add `127.0.0.1` to the allowlist:
   ```properties
   ssrf.allowed-domains=hooks.slack.com,...,127.0.0.1
   ```
2. In `WebhookService.testWebhook()`, comment out the guard call:
   ```java
   // ssrfGuard.validate(webhook.getUrl());
   ```

Restart and fire:

```bash
curl -s -X POST http://localhost:8080/api/webhooks/3/test \
  -H "Authorization: Bearer $TOKEN"
# The server attempts to call https://127.0.0.1:8080/actuator/env on your behalf.
# On a cloud instance, point the URL at:
# https://169.254.169.254/latest/meta-data/iam/security-credentials/
# to retrieve temporary IAM credentials from the metadata service.
```

### Step 5 — Restore the guard and confirm 422

Revert both changes (remove `127.0.0.1` from the allowlist, uncomment `ssrfGuard.validate()`), then restart:

```bash
# (TOKEN obtained in Step 2)

curl -s -X POST http://localhost:8080/api/webhooks/3/test \
  -H "Authorization: Bearer $TOKEN"
# → 422 {"error":"Host is not on the webhook allowlist"}
```

### Step 6 — Test the AWS metadata endpoint

```bash
# (TOKEN obtained in Step 2)

curl -s -X POST http://localhost:8080/api/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://169.254.169.254/latest/meta-data/"}'
# → 201 (stored)

curl -s -X POST http://localhost:8080/api/webhooks/4/test \
  -H "Authorization: Bearer $TOKEN"
# → 422 {"error":"Host is not on the webhook allowlist"}
# Even if you added 169.254.169.254 to the allowlist, the IP-range check
# would still block it: isLinkLocalAddress() returns true for 169.254.x.x.
```

### Step 7 — Trace `SsrfGuard` in `SsrfGuardTest`

Open `api/src/test/java/com/securetask/SsrfGuardTest.java`. All tests instantiate `SsrfGuard` directly — no Spring context needed. The constructor takes a `List<String>` of allowed domains, so tests can pass a custom list without loading `application.properties`. Literal IP addresses are parsed by `InetAddress.getByName()` without a DNS query, so these tests run fully offline.

### Step 8 — Understand the ID enumeration guard

Open `WebhookService.delete()` and `testWebhook()`. Both use `findByIdAndUser()` which returns `Optional.empty()` for both "webhook not found" and "webhook belongs to a different user". The controller maps both cases to 404. This prevents an attacker from learning whether a given webhook ID exists by observing the response code.

---

## Manual test checklist

| Request | Expected status |
|---------|----------------|
| `POST /api/webhooks` (authenticated, any URL) | 201 |
| `POST /api/webhooks` (unauthenticated) | 401 |
| `GET /api/webhooks` (authenticated) | 200 |
| `GET /api/webhooks` (unauthenticated) | 401 |
| `DELETE /api/webhooks/{id}` (own webhook) | 204 |
| `DELETE /api/webhooks/{id}` (another user's webhook) | 404 |
| `POST /api/webhooks/{id}/test` (url = `https://attacker.example.com`) | 422 — not on allowlist |
| `POST /api/webhooks/{id}/test` (url = `http://hooks.slack.com/...`) | 422 — http not allowed |
| `POST /api/webhooks/{id}/test` (url = `https://127.0.0.1/`) | 422 — not on allowlist |
| `POST /api/webhooks/{id}/test` (url = `https://169.254.169.254/`) | 422 — not on allowlist |
| `POST /api/webhooks/{id}/test` (url = `https://hooks.slack.com/...`) | 200 — allowlisted |
| `POST /api/webhooks/{id}/test` (unauthenticated) | 401 |
| `POST /api/webhooks/99999/test` (non-existent) | 404 |

---

## Expected results table

| Caller | URL | Guard layer that fires | HTTP status |
|--------|-----|----------------------|------------|
| Authenticated | `http://hooks.slack.com/` | Scheme — not https | 422 |
| Authenticated | `https://attacker.example.com/` | Allowlist — not listed | 422 |
| Authenticated | `https://127.0.0.1/` | Allowlist — not listed | 422 |
| Authenticated | `https://169.254.169.254/` | Allowlist — not listed | 422 |
| Authenticated | `https://192.168.1.1/` | Allowlist — not listed | 422 |
| Authenticated | `file:///etc/passwd` | Scheme — not https | 422 |
| Authenticated | `https://hooks.slack.com/services/…` | Passes all checks | 200 |
| Authenticated | `https://webhooks.discord.com/api/…` | Passes (suffix match on `discord.com`) | 200 |
| Unauthenticated | any | — | 401 |
| Non-owner / missing ID | any | — | 404 |

---

## Common mistakes

### Checking the string instead of the resolved address

```java
// WRONG — trivially bypassed
if (url.contains("127.0.0.1") || url.contains("localhost")) { ... }
```

Bypasses: `https://127.1/`, `https://[::1]/`, `https://internal.corp/` (resolves to 10.x.x.x).

Always resolve the hostname and check the resulting `InetAddress`. The allowlist provides an outer gate, but the IP-range check is the defence-in-depth that catches cases where an allowlisted name resolves unexpectedly.

### Forgetting IPv6

`::1` is the IPv6 loopback and resolves correctly via `InetAddress.getByName("[::1]")`. Java's `isLoopbackAddress()` covers it — but only if you actually call `InetAddress.getByName()` rather than trying to parse the string yourself.

### Not blocking the link-local range

`169.254.0.0/16` is link-local. `isLinkLocalAddress()` covers the entire subnet — not just the AWS metadata IP. Docker's default bridge gateway (`172.17.0.1`) is site-local and covered by `isSiteLocalAddress()`.

### Allowing plain HTTP

Allowing `http://` means credentials travel in the clear and the attacker can reach any HTTP service, not just HTTPS ones. HTTPS-only reduces the attack surface and is the right production default for outbound webhook calls.

### Allowing redirects

`HttpClientConfig` explicitly sets `instanceFollowRedirects(false)`. Without this, an attacker could register a legitimately allowlisted URL that returns `301 Location: https://169.254.169.254/` — the guard validates the *registered* URL, but the HTTP client then follows the redirect to the internal address. Always disable redirect following on the HTTP client used for user-triggered outbound calls.

### No timeout

An attacker can point a webhook at a slow host to hold threads open indefinitely. The `outboundHttpClient` bean sets a 5-second connect and 10-second read timeout — do not remove these.

### Accepting URLs with userinfo

A URL such as `https://allowed.com@evil.com/` is syntactically valid. Java's `URI.getHost()` correctly returns `evil.com`, so the allowlist check catches this particular form. However, userinfo in a webhook URL is never legitimate and should be rejected explicitly to prevent parser edge-case surprises in other URL libraries:

```java
if (uri.getUserInfo() != null) {
    throw new BlockedUrlException("URLs with userinfo are not permitted");
}
```

### Checking only the first resolved IP address

`InetAddress.getByName(host)` returns one address. A hostname with multiple A records (DNS round-robin) could return a public IP at validation time but route to a different IP at connection time. For stricter protection, use `InetAddress.getAllByName(host)` and verify **every** resolved address — if any one is internal, reject the entire request.

---

## Discussions

**Q1: Why does registration accept any URL but the test endpoint is the one that blocks?**

The SSRF risk is the *outbound HTTP call*, not the storage. Storing a URL is harmless; calling it is what causes damage. Validating only at fire time makes the exploit flow explicit — an attacker must trigger the test endpoint to get a response. In production you might add registration-time validation too (fast feedback for the user), but the guard at the call site is the critical control.

**Q2: Why an allowlist rather than a blocklist?**

A blocklist requires you to enumerate every dangerous target — internal IPs, cloud metadata addresses, internal DNS names, IPv6 variants, octal notation, etc. It is an open-ended enumeration problem; attackers look for gaps. An allowlist inverts the problem: the server calls *nothing* unless it is explicitly approved. The security-relevant question changes from "did we block everything bad?" to "did we approve only good targets?" — a much smaller and more auditable set.

**Q3: Why suffix matching rather than exact hostname matching?**

Some services use dynamic subdomains for their webhook endpoints. Microsoft Teams, for example, uses `{tenant}.webhook.office.com` — the subdomain is tenant-specific. Suffix matching on `webhook.office.com` covers all tenant URLs without listing each one. The match is anchored with a leading dot (`h.endsWith("." + domain)`) so `evilwebhook.office.com` does not match `webhook.office.com`.

**Q4: Why return 422 Unprocessable Entity instead of 400 Bad Request?**

400 means the request was syntactically malformed. 422 means the request was syntactically valid but semantically rejected by the server's business rules. A URL like `https://127.0.0.1/` is a perfectly valid URL — the server chose not to call it, which is a business-rule rejection.

**Q5: Why does `findByIdAndUser` return 404 for a webhook owned by another user instead of 403?**

403 confirms that the resource exists but the caller lacks permission. An attacker observing the difference between 403 (exists, not yours) and 404 (does not exist) can enumerate valid webhook IDs by trying sequential integers. Returning 404 in both cases removes that signal.

**Q6: What is DNS rebinding and why doesn't the current fix prevent it?**

In a DNS rebinding attack the attacker controls a domain that is on the allowlist (or passes some other check). Its DNS TTL is set very short. At validation time it resolves to a legitimate public IP (passes the allowlist and IP-range checks). By the time the HTTP client makes the actual TCP connection the attacker has changed the DNS record to point at an internal address. The time gap between `InetAddress.getByName()` and the connection is the attack window.

Prevention requires validating the IP of the *actual TCP connection*, not just the pre-connection DNS result. This is complex (it requires a custom HTTP client or a socket factory that hooks into the connect step) and is out of scope for this lab. The allowlist significantly reduces the risk surface: only attacker-controlled allowlisted domains can attempt rebinding.

A more robust mitigation is **DNS pinning**: resolve the hostname once before the request, then instruct the HTTP client to connect to exactly those IPs without issuing another DNS query. This closes the TOCTOU window. Implementing DNS pinning in Java requires a custom `SocketFactory` — it is an advanced hardening step beyond what this lab implements.

**Q7: Why does resolving `InetAddress.getByName("127.0.0.1")` not make a DNS query?**

`InetAddress.getByName()` checks whether the argument is a valid numeric IP literal first. If it is, it parses it directly without sending a DNS query. This is why `SsrfGuardTest` unit tests run fully offline — they use literal IP addresses, not hostnames.

**Q8: Why is the `OutboundHttpClient` a `@FunctionalInterface` rather than using `RestClient` directly?**

`RestClient` has a fluent builder API that is awkward to mock in tests. Wrapping it in a single-method interface lets `@MockBean` replace the entire HTTP call with a stub in `WebhookControllerTest`. The `SsrfGuard` still runs for real in those tests — only the actual network I/O is mocked — so the integration tests exercise the full validation path without touching the network.

**Q9: What additional controls limit damage even after a request passes the guard?**

Even a legitimately allowlisted webhook endpoint can misbehave. Defence-in-depth controls:

- **Response size limit**: cap bytes read from the response body. Without a limit, a slow endpoint streaming gigabytes will exhaust heap memory.
- **Content-Type validation**: reject unexpected content types (e.g. binary data when JSON is expected). Feeding unexpected input into a parser can trigger bugs unrelated to SSRF.
- **Network-level egress rules**: an egress firewall that blocks `169.254.169.254` and RFC 1918 ranges at the infrastructure level acts as a safety net if the application-level guard is bypassed. Application-level and network-level controls are complementary — neither replaces the other.
- **Short timeouts**: already applied in `HttpClientConfig` — 5 s connect, 10 s read.

**Q10: Why should raw IP addresses not appear in the production allowlist?**

The production `ssrf.allowed-domains` list contains only domain names. Allowing raw IPs:

1. Bypasses the DNS → IP-range-check pipeline. The allowlist's job is to name trusted services; the IP-range check's job is to verify they resolve safely. Putting an IP directly on the allowlist skips the second step.
2. IP addresses of third-party services change. Hardcoding them creates a maintenance burden.
3. Attackers may operate on the same public IP via virtual hosting; approving an IP is broader than approving a domain.

Raw IPs appear only in `@TestPropertySource` overrides in `SsrfGuardTest` and `WebhookControllerTest`, where literal IPs let offline tests reach the IP-range defence-in-depth check without requiring DNS.
