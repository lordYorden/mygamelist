# Lab 02 — JWT Authentication

## Learning goals

By the end of this lab you will be able to:

1. Explain the difference between stateless JWT Bearer authentication and stateful session-based authentication, and identify which client types benefit from each.
2. Describe the BFF (Backend for Frontend) pattern and why it keeps JWTs off the browser entirely.
3. Explain the security risks of storing JWTs in `localStorage` or `sessionStorage` and what XSS can do with them.
4. Configure short-lived access tokens and longer-lived refresh tokens, and reason about appropriate expiry values.
5. Describe why JWT secrets must be loaded from a secrets manager rather than hard-coded in source or config files.
6. Demonstrate an `alg:none` algorithm substitution attack and explain why the server must pin the expected algorithm.
7. Explain refresh token rotation and how it limits the blast radius when a refresh token is stolen.

---

## Background

### Why JWT for non-browser clients?

Session-based authentication relies on a server-side session store (in-memory or database) and a `JSESSIONID` cookie that the browser sends automatically. This works well for browsers — cookies are attached to same-origin requests with no extra code.

API clients (mobile apps, CLIs, microservices) face a different reality:

- They do not automatically manage cookies.
- They may call the API from domains that are not the origin that set the cookie.
- They need to authenticate independently of a browser session.

JSON Web Tokens (JWTs) solve this by encoding the identity and authorisation claims directly inside a signed token. The client stores the token and attaches it as an `Authorization: Bearer <token>` header. The server verifies the signature and trusts the claims — no session store lookup required.

### The BFF insight

A common mistake is to have the browser itself call the token endpoint and store the resulting JWT in `localStorage` or a JavaScript-accessible cookie. This directly exposes the token to any XSS payload running on the page.

The **Backend for Frontend** (BFF) pattern avoids this: the browser speaks only to its own server-side backend using session cookies. That backend calls downstream APIs with JWT Bearer tokens. The browser never sees a JWT at all.

SecureTask uses a hybrid approach:
- **Browser clients** access the application through the BFF at port 8081. The BFF manages server-side sessions and calls the main API with JWT Bearer tokens. The browser never sees a JWT.
- **API clients** (mobile, CLI, other services) call `POST /api/auth/token` to obtain JWT tokens and use `Authorization: Bearer` for subsequent requests.

### Vulnerable patterns

The following patterns are intentionally absent from this implementation. Understanding them is part of the learning.

#### localStorage storage

```javascript
// VULNERABLE — any XSS on the page can read this
localStorage.setItem('accessToken', token.accessToken);
fetch('/api/tasks', {
    headers: { Authorization: 'Bearer ' + localStorage.getItem('accessToken') }
});
```

A cross-site scripting payload can call `localStorage.getItem('accessToken')` and exfiltrate the token to an attacker-controlled server.

#### No expiry

```java
// VULNERABLE — token lives forever
JwtClaimsSet claims = JwtClaimsSet.builder()
        .subject(user.getUsername())
        // Missing: .expiresAt(...)
        .build();
```

Without an `exp` claim a stolen token is valid indefinitely.

#### Hard-coded secret

```properties
# VULNERABLE — leaks via version control, logs, environment variable dumps
jwt.secret=my-super-secret-key
```

Secrets in property files end up in git history, Docker images, and log aggregators. Anyone who can read the secret can forge arbitrary tokens.

#### Algorithm substitution (alg:none)

```java
// VULNERABLE — accepts any algorithm the token claims
// If the server does not pin the expected algorithm, an attacker can craft:
// Header: {"alg":"none"}  Payload: {"sub":"admin","roles":["ROLE_ADMIN"]}
// Signature: (empty)
// The server skips signature verification because alg=none means "unsigned".
```

The fix: `NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256)` — the decoder only accepts HS256 tokens.

#### No refresh token rotation

```java
// VULNERABLE — refresh token is valid forever after issue
// If Bob steals Alice's refresh token, he can obtain new access tokens
// even after Alice rotates her password.
```

With rotation, each use of a refresh token invalidates the old one and issues a new one. If a stolen token is used, Alice's next refresh attempt fails — a signal that the token was compromised.

---

## Relevant files

| File | Purpose |
|------|---------|
| `api/src/main/java/com/securetask/config/JwtConfig.java` | Configures `JwtDecoder`, `JwtEncoder`, and `JwtAuthenticationConverter` beans |
| `api/src/main/java/com/securetask/config/SecretsManagerConfig.java` | Loads JWT secret from AWS Secrets Manager at startup |
| `api/src/main/java/com/securetask/security/SecurityConfig.java` | Adds `.oauth2ResourceServer(...)` so Bearer tokens are accepted alongside sessions |
| `api/src/main/java/com/securetask/service/JwtService.java` | Issues access tokens, manages refresh token lifecycle (issue, rotate, revoke) |
| `api/src/main/java/com/securetask/service/UnauthorizedException.java` | Typed exception for invalid/expired refresh token scenarios |
| `api/src/main/java/com/securetask/entity/RefreshToken.java` | JPA entity storing the SHA-256 hash of the refresh token (never the raw token) |
| `api/src/main/java/com/securetask/repository/RefreshTokenRepository.java` | Spring Data repository for refresh token CRUD |
| `api/src/main/java/com/securetask/controller/TokenController.java` | Exposes `POST /api/auth/token`, `/refresh`, `/revoke` |
| `api/src/main/java/com/securetask/dto/TokenRequest.java` | Request body for `POST /api/auth/token` |
| `api/src/main/java/com/securetask/dto/TokenResponse.java` | Response containing `accessToken`, `refreshToken`, `expiresIn` |
| `api/src/main/java/com/securetask/dto/RefreshRequest.java` | Request body for `/refresh` and `/revoke` |
| `localstack/init/03-create-jwt-secret.sh` | Seeds the JWT secret into LocalStack Secrets Manager |

---

## How the fix works

### 1. Secret management

The JWT signing key is never in source code. `SecretsManagerConfig` fetches it from Secrets Manager at startup and exposes it as a `@Bean("jwtSecret")`. Tests override this bean via `TestSecretsManagerConfig` so no AWS call is made during testing.

### 2. Token issuance

`JwtService.issueTokenPair()` creates two tokens:

- **Access token** — a short-lived (15 minutes by default) HS256-signed JWT containing the user's username and roles. The server does not store it; verification is purely by signature check.
- **Refresh token** — a random 32-byte URL-safe Base64 string. Only the SHA-256 hash is stored in the database (`refresh_tokens` table). The raw token is sent to the client once and never stored server-side.

### 3. Filter chain

`SecurityConfig` adds `.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` to the filter chain. Spring Security's `BearerTokenAuthenticationFilter` inspects every request for an `Authorization: Bearer` header. The main API is fully stateless — it accepts only JWT Bearer tokens. Session-based access happens through the BFF, which exchanges the session for a Bearer token before calling the main API.

### 4. CSRF exemption

The token endpoints (`/api/auth/token`, `/api/auth/refresh`, `/api/auth/revoke`) are CSRF-exempt because:
- They are called by API clients that do not have a browser session.
- They use `application/json` bodies, not form submissions.
- They do not rely on cookies for authentication.

### 5. Refresh token rotation

`JwtService.validateAndRotateRefresh()` atomically deletes the presented refresh token and issues a new pair. This means each refresh token is single-use. If an attacker replays a stolen token, the legitimate user's next refresh attempt fails with 401, alerting them that something is wrong.

### 6. Algorithm pinning

`NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256)` configures the decoder to only accept tokens signed with HS256. Tokens with `"alg":"none"` or any other algorithm are rejected with a 401 before any claims are read.

---

## Step-by-step guide

### Prerequisites

Start PostgreSQL and LocalStack (which seeds the JWT secret):

```bash
docker compose up -d postgres localstack
```

Start the application:

```bash
AWS_REGION=us-east-1 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
SECRETS_MANAGER_ENDPOINT=http://localhost:4566 \
DB_SECRET_NAME=securetask/db \
JWT_SECRET_NAME=securetask/jwt \
./gradlew :api:bootRun
```

Register a user if one does not exist:

```bash
curl -s -X POST http://localhost:8080/api/register \
  -H 'Content-Type: application/json' \
  -H 'X-XSRF-TOKEN: dummy' \
  -b 'XSRF-TOKEN=dummy' \
  -d '{"username":"alice","email":"alice@example.com","password":"password123"}'
```

(The main API uses `CookieCsrfTokenRepository`, which is stateless — it just checks that the `XSRF-TOKEN` cookie value matches the `X-XSRF-TOKEN` header. Sending matching dummy values satisfies the check.)

---

### Step 1: Get a token pair

```bash
curl -s -X POST http://localhost:8080/api/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}' | jq .
```

**Expected result:**

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiJ9...",
  "tokenType": "Bearer",
  "expiresIn": 900,
  "refreshToken": "xK3p..."
}
```

Save the tokens:

```bash
ACCESS=$(curl -s -X POST http://localhost:8080/api/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}' | jq -r .accessToken)

REFRESH=$(curl -s -X POST http://localhost:8080/api/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}' | jq -r .refreshToken)
```

---

### Step 2: Call a protected API endpoint with Bearer token

```bash
curl -s http://localhost:8080/api/tasks \
  -H "Authorization: Bearer $ACCESS" | jq .
```

**Expected result:** HTTP 200 with your task list (empty array if no tasks yet).

---

### Step 3: Tamper with the token

Decode the payload, change a claim, re-encode without updating the signature:

```bash
# Split the token
HEADER=$(echo $ACCESS | cut -d. -f1)
PAYLOAD=$(echo $ACCESS | cut -d. -f2)
SIG=$(echo $ACCESS | cut -d. -f3)

# Decode and modify payload — change subject to "eve"
MODIFIED_PAYLOAD=$(echo $PAYLOAD | base64 -d 2>/dev/null | sed 's/"alice"/"eve"/' | base64 | tr -d '=' | tr '+/' '-_')

# Re-assemble with original signature
TAMPERED="${HEADER}.${MODIFIED_PAYLOAD}.${SIG}"

curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/tasks \
  -H "Authorization: Bearer $TAMPERED"
```

**Expected result:** `401` — the signature no longer matches the modified payload.

---

### Step 4: Try an alg:none token

```bash
ALG_NONE_TOKEN="eyJhbGciOiJub25lIn0.eyJzdWIiOiJhbGljZSIsInJvbGVzIjpbIlJPTEVfVklFV0VSIl0sImlzcyI6InNlY3VyZXRhc2siLCJpYXQiOjE3MDAwMDAwMDAsImV4cCI6OTk5OTk5OTk5OX0."

curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/tasks \
  -H "Authorization: Bearer $ALG_NONE_TOKEN"
```

**Expected result:** `401` — the decoder rejects any token not signed with HS256.

---

### Step 5: Refresh and rotate

```bash
NEW_TOKENS=$(curl -s -X POST http://localhost:8080/api/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refreshToken\":\"$REFRESH\"}")

echo $NEW_TOKENS | jq .

NEW_ACCESS=$(echo $NEW_TOKENS | jq -r .accessToken)
NEW_REFRESH=$(echo $NEW_TOKENS | jq -r .refreshToken)

# Verify the new access token works
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/tasks \
  -H "Authorization: Bearer $NEW_ACCESS"
```

**Expected result:** The refresh returns a new token pair. Using the original `$REFRESH` again returns 401.

```bash
# Reuse of the old refresh token must fail
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8080/api/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refreshToken\":\"$REFRESH\"}"
```

**Expected result:** `401`

---

### Step 6: Confirm session auth still works

Open `http://localhost:8081/login.html` in a browser, log in as alice, and verify the dashboard loads normally. The BFF's session-based authentication runs independently of the main API's JWT setup — the two mechanisms coexist.

---

## Manual test checklist

- [ ] `POST /api/auth/token` with valid credentials returns 200 with `accessToken` and `refreshToken`
- [ ] `POST /api/auth/token` with wrong password returns 401
- [ ] `GET /api/tasks` with a valid Bearer token returns 200
- [ ] `GET /api/tasks` with a tampered Bearer token (bad signature) returns 401
- [ ] `GET /api/tasks` with an `alg:none` token returns 401
- [ ] `POST /api/auth/refresh` with a valid refresh token returns 200 with new tokens
- [ ] `POST /api/auth/refresh` with the same refresh token a second time returns 401
- [ ] `POST /api/auth/revoke` returns 200; subsequent `POST /api/auth/refresh` returns 401
- [ ] Browser session login still works after JWT changes

---

## Expected results table

| Scenario | Endpoint | Expected status |
|----------|----------|-----------------|
| Valid credentials | `POST /api/auth/token` | 200 |
| Wrong password | `POST /api/auth/token` | 401 |
| Valid Bearer token | `GET /api/tasks` | 200 |
| Tampered payload | `GET /api/tasks` | 401 |
| alg:none token | `GET /api/tasks` | 401 |
| Valid refresh token | `POST /api/auth/refresh` | 200 |
| Reused refresh token | `POST /api/auth/refresh` | 401 |
| Expired refresh token | `POST /api/auth/refresh` | 401 |
| After revoke | `POST /api/auth/refresh` | 401 |

---

## Common mistakes

1. **Storing JWT in `localStorage`** — Any XSS payload can call `localStorage.getItem` and exfiltrate the token. Use `httpOnly` cookies for browser clients, or the BFF pattern so the browser never sees a JWT.

2. **Long-lived or non-expiring access tokens** — The `exp` claim exists for a reason. A stolen access token without an expiry is equivalent to a permanent password. Keep access tokens short (minutes to 15 minutes) and rely on refresh tokens for long-lived sessions.

3. **Hard-coding the JWT secret** — A secret in `application.properties` is one git push away from being public. Use a secrets manager, environment variable injection at deploy time, or a Kubernetes Secret mounted as a volume.

4. **Not pinning the algorithm** — Nimbus JWT (and many older libraries) accept whatever algorithm the token header claims. Always call `.macAlgorithm(MacAlgorithm.HS256)` (or its asymmetric equivalent) to prevent algorithm substitution attacks.

5. **Forgetting CSRF exemption for token endpoints** — `POST /api/auth/token` is called by API clients that have no session and no CSRF cookie. If you forget to exempt it, every token request returns 403. The exemption is safe because the endpoint is not protected by session cookies.

---

## Discussion questions

**Q1: When should you prefer JWT over session cookies, and when should you prefer session cookies over JWT?**

Sessions are simpler, easier to revoke instantly (just delete the session record), and require no client-side token management. They are the right choice for browser-facing applications.

JWTs are better for API clients (mobile apps, CLIs, service-to-service calls) where cookie management is awkward, especially across origins or on platforms without a native cookie jar. The trade-off is that JWTs are harder to revoke before expiry — once issued, the server cannot invalidate an access token without adding a revocation list (which reintroduces statefulness).

**Q2: Why is the BFF pattern recommended for browser clients instead of having the browser call `/api/auth/token` directly?**

If the browser calls the token endpoint, it must store the JWT somewhere — `localStorage`, `sessionStorage`, or a JavaScript-readable cookie. Any XSS vulnerability on the page can then steal the token. The BFF pattern keeps JWTs on the server and gives the browser only a `httpOnly` session cookie, which JavaScript cannot read. This dramatically reduces the impact of XSS.

**Q3: How does refresh token rotation limit the damage if a refresh token is stolen?**

With rotation, each refresh token is single-use. When the attacker uses the stolen token to get a new pair, the victim's next legitimate refresh attempt fails with 401. This tells the system that the token was used by someone else. Without rotation, the attacker could silently use the token indefinitely alongside the victim.

For even stronger security, detect reuse: if a refresh token that was already consumed is presented again, it is a sign that either the client or the attacker is replaying an old token. Some systems respond by revoking the entire token family (all refresh tokens for that user).

**Q4: What exactly does an `alg:none` attack exploit, and why does algorithm pinning prevent it?**

The JWT header contains an `"alg"` field. Libraries that blindly trust this field will skip signature verification when `"alg":"none"` is present, because the spec allows unsigned tokens. An attacker can craft a token with any claims they like, set `"alg":"none"`, and send it to a vulnerable server with no signature at all.

Algorithm pinning prevents this by configuring the decoder to only accept tokens signed with a specific algorithm. `NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256)` explicitly instructs Nimbus to reject any token whose header does not specify HS256 — including `"alg":"none"` tokens.

**Q5: Where should a mobile application store its JWT access token and refresh token?**

On iOS, use the **Keychain** (via `SecItemAdd` / `SecItemCopyMatching`), which is encrypted by the Secure Enclave and isolated per application. On Android, use the **EncryptedSharedPreferences** backed by the Android Keystore, which ties the encryption key to the device hardware.

Never use plain `SharedPreferences` on Android or plain `UserDefaults` on iOS — both are unencrypted on disk and readable by any app with root access or a backup extraction tool. Never store tokens in local SQLite databases without encryption for the same reason.
