# Lab 01 — Authentication

## Learning goals

By the end of this lab you will be able to:

- Explain why password hashing is necessary and how Argon2 compares to MD5, SHA-1, and BCrypt.
- Describe the risk of storing raw passwords or weak hashes.
- Implement registration and login using Spring Security.
- Explain the first-user bootstrap pattern and why it avoids hard-coded admin credentials.
- Identify how mass-assignment is prevented by using DTOs.
- Describe how the BFF session cookie works and why it should be `HttpOnly` and `SameSite=Strict`.

---

## Background

Authentication answers the question: _who are you?_

Common authentication mistakes:

| Mistake | Consequence |
|---------|-------------|
| Storing plain-text passwords | One database leak exposes every user's password |
| Using MD5 or SHA-1 | GPU cracking at billions of hashes/second |
| Using BCrypt with cost=4 | Too fast; an attacker can brute-force offline |
| Hard-coded admin password | Credential leaks in version control and Docker images |
| Binding request bodies directly to JPA entities | Clients can set fields like `role` or `id` |

---

## Relevant files

| File | Purpose |
|------|---------|
| `api/src/main/java/com/securetask/entity/User.java` | JPA entity — note that role is not settable by the client |
| `api/src/main/java/com/securetask/dto/RegisterRequest.java` | Inbound DTO — the only fields the client may provide |
| `api/src/main/java/com/securetask/dto/UserResponse.java` | Outbound DTO — passwordHash is intentionally absent |
| `api/src/main/java/com/securetask/service/UserService.java` | Business logic — role assignment, hashing |
| `api/src/main/java/com/securetask/security/SecurityConfig.java` | Spring Security filter chain (JWT Bearer, stateless) |
| `api/src/main/java/com/securetask/security/SecureTaskUserDetailsService.java` | Bridges User entity to Spring Security |
| `api/src/main/java/com/securetask/controller/AuthController.java` | REST endpoints `/api/register` and `/api/me` |
| `bff/src/main/java/com/securetask/bff/controller/SessionController.java` | BFF login/logout — sets and clears the `BFF-SESSION` cookie |
| `frontend/register.html` | Registration form |
| `frontend/login.html` | Login form |
| `frontend/dashboard.html` | Protected page |
| `frontend/js/api.js` | Fetch wrapper — handles CSRF token |
| `frontend/js/auth.js` | Page-level auth logic |
| `frontend/js/dom.js` | Safe DOM helpers (textContent only) |

---

## Security risks addressed

### 1. Weak password storage
Passwords are hashed with **Argon2id** using Spring Security's `Argon2PasswordEncoder`. Argon2 is memory-hard, making GPU-accelerated cracking economically impractical.

### 2. Hard-coded credentials
No admin password is seeded into the database or stored in any configuration file. The first user to register becomes ADMIN, and that assignment is made at runtime.

### 3. Mass assignment
The registration endpoint accepts a `RegisterRequest` DTO, not a `User` entity. The client cannot set `role`, `id`, or `createdAt` regardless of what JSON they send.

### 4. Password hash exposure
`UserResponse` has no `passwordHash` field. The hash is never serialized or returned by any API endpoint.

### 5. Session security
The BFF session cookie (`BFF-SESSION`) is marked `HttpOnly` (JavaScript cannot read it) and `SameSite=Strict` (it is not sent on cross-site requests). The main API itself is fully stateless and issues no cookies.

---

## Step-by-step implementation guide

> **Note:** The implementation is already complete. Use these steps to understand what was built, or to re-implement it yourself from scratch.

### Step 1 — Understand the DTO boundary

Open `api/src/main/java/com/securetask/dto/RegisterRequest.java`. Notice that it only has `username`, `email`, and `password`. There is no `role` field.

**Question:** What would happen if you used the `User` entity directly as the `@RequestBody` parameter?

### Step 2 — Trace the registration flow

1. Browser submits the registration form → BFF receives `POST /api/register`
2. BFF's `ApiProxyController` forwards the request to the main API at `http://localhost:8080/api/register`, adding a service token.
3. Main API's `AuthController.register()` receives the forwarded request.
4. Spring validates the `@Valid @RequestBody RegisterRequest`.
5. `UserService.register()` checks for duplicate username/email.
6. If this is the first user (`countUsers() == 0`), role is set to `ADMIN`; otherwise `VIEWER`.
7. The password is hashed: `passwordEncoder.encode(request.getPassword())`.
8. The `User` entity is saved.
9. A `UserResponse` (no hash) is returned.

### Step 3 — Inspect the password hash

After registering a user, query the database directly:

```bash
psql -h localhost -U securetask_user -d securetask -c "SELECT username, password_hash FROM users;"
```

You should see something like:

```
 username | password_hash
----------+-----------------------------------------------
 alice    | {argon2}$argon2id$v=19$m=65536,t=3,p=1$...
```

The raw password `password123` must not appear anywhere in that string.

### Step 4 — Verify the /api/me response

Use JWT Bearer tokens to call the main API directly:

```bash
# Get a token
ACCESS=$(curl -s -X POST http://localhost:8080/api/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"password123"}' | jq -r .accessToken)

# Call /api/me with the Bearer token
curl -s http://localhost:8080/api/me -H "Authorization: Bearer $ACCESS"
```

Confirm the response JSON contains `username`, `email`, `role`, and `createdAt` — but **not** `passwordHash` or `password`.

### Step 5 — Test unauthenticated access

Without a token:

```bash
curl -i http://localhost:8080/api/me
```

Expected: `HTTP/1.1 401`

### Step 6 — Test the first-user bootstrap

1. Truncate the users table: `DELETE FROM users;`
2. Register a new account at `/register.html`.
3. Log in and call `/api/me` — the role should be `ADMIN`.
4. Register a second account.
5. Log in with the second account and call `/api/me` — the role should be `VIEWER`.

### Step 7 — Read the security filter chain

Open `api/src/main/java/com/securetask/security/SecurityConfig.java`. Find the `authorizeHttpRequests` section.

**Question:** What is "deny by default"? Which line in the configuration enforces it?

---

## Manual test checklist

- [ ] Register at http://localhost:8081/register.html — first account gets ADMIN role
- [ ] Register a second account — gets VIEWER role
- [ ] Log in at http://localhost:8081/login.html and reach the dashboard
- [ ] Open http://localhost:8081/dashboard.html without logging in — the BFF returns 401
- [ ] Call `GET /api/me` without a token — returns 401
- [ ] Check the database: password_hash column starts with `{argon2}`, not plaintext
- [ ] Inspect the `/api/me` JSON response: no `passwordHash` field present

---

## Expected results

| Test | Expected |
|------|----------|
| First registered user | `role: "ADMIN"` |
| Second registered user | `role: "VIEWER"` |
| `/api/me` (unauthenticated) | `401 Unauthorized` |
| `/api/me` (authenticated with Bearer token) | `200 OK`, JSON with no `passwordHash` |
| Password column in DB | Starts with `{argon2}` |
| Sending `"role":"ADMIN"` in registration body | Ignored — role is assigned server-side |

---

## Common mistakes

**Mistake:** Using `@RequestBody User user` instead of `@RequestBody RegisterRequest request`.
**Why it matters:** The client can set any field on the entity, including `role`, `id`, or other sensitive fields — a mass-assignment vulnerability.

**Mistake:** Returning `User` instead of `UserResponse` from the API.
**Why it matters:** The password hash, and any future sensitive fields, would be serialized into the response.

**Mistake:** Using BCrypt with a low cost factor (cost=4).
**Why it matters:** A low cost factor makes BCrypt fast enough to brute-force on modern hardware.

**Mistake:** Hard-coding an admin password in `application.properties` or `data.sql`.
**Why it matters:** Credentials in version control or Docker images are easily leaked. The first-user bootstrap pattern eliminates this risk entirely.

**Mistake:** Not marking session cookies as `HttpOnly`.
**Why it matters:** JavaScript running on the page (including injected XSS scripts) can read the cookie and hijack the session.

---

## Discussions

**Q1: Why is Argon2 considered more secure than BCrypt for password hashing?**

BCrypt was designed in 1999. It is intentionally slow, but it only uses about 4 KB of memory per hash regardless of the cost factor. That limitation matters because modern GPU cards have thousands of cores, and each core can run a BCrypt computation independently — the memory fits easily in a single core's cache. An attacker with a GPU farm can therefore run millions of BCrypt hashes in parallel.

The cost factor controls how many internal iterations BCrypt performs (`2^cost`):

| Cost | Iterations | Approximate time per hash |
|------|-----------|--------------------------|
| 4 | 16 | ~1 ms |
| 10 | 1,024 | ~100 ms |
| 12 | 4,096 | ~400 ms |

At cost=4, a single modern GPU can compute roughly one million hashes per second. An attacker can try every dictionary word, every common password variation, and every short alphanumeric combination in seconds or minutes.

Argon2 is **memory-hard**. By default it requires 64 MB of memory per hash. A GPU with 8 GB of RAM and 4,096 cores can only run approximately 128 Argon2 hashes in parallel (8,000 MB ÷ 64 MB), instead of thousands. The GPU hardware advantage that makes BCrypt cracking fast is largely neutralized.

Argon2 also won the Password Hashing Competition in 2015, a public competition specifically designed to find the best algorithm for this purpose.

In short: BCrypt slows the attacker down in time. Argon2 slows them down in both time and memory, which is what defeats GPU-based attacks.

**Q2: What is a mass-assignment vulnerability? Find the line in this codebase that prevents one.**

A mass-assignment vulnerability occurs when a web framework automatically binds all fields from a client request directly onto a server-side object — including fields the client should never be allowed to set.

Example of the vulnerable pattern:
```java
// WRONG — the client can send {"username":"alice","role":"ADMIN"} and it sticks
@PostMapping("/register")
public User register(@RequestBody User user) {
    return userRepository.save(user);
}
```

Because `User` has a `role` field, any client can register themselves as ADMIN by including `"role":"ADMIN"` in the JSON body.

The line in this codebase that prevents it is in `AuthController.java`:
```java
public ResponseEntity<?> register(@Valid @RequestBody RegisterRequest request)
```

`RegisterRequest` only has `username`, `email`, and `password`. There is no `role` field. No matter what JSON the client sends, they cannot influence the role. The role is assigned exclusively in `UserService.register()` based on server-side logic.

**Q3: The `countUsers()` check is inside a `@Transactional` method. Why is this important for concurrent registrations?**

Without a transaction, two users registering at the exact same millisecond could both run `countUsers()` before either has committed. Both would see `count = 0`, both would be assigned `ADMIN`, and both would save successfully. The database would then contain two admins from the very first registration.

Wrapping the entire operation in a single transaction with `SERIALIZABLE` isolation closes this window. PostgreSQL's Serializable Snapshot Isolation (SSI) tracks which transactions read which data. If two transactions both read an empty users table and both try to insert, PostgreSQL detects that allowing both to commit would produce a result that could not have happened if they had run one after the other — and it aborts one of them.

The aborted transaction throws an exception, which the caller catches. Only one registration succeeds as ADMIN. All others either succeed as VIEWER (if they ran after the first commit) or fail and can be retried.

The `@Transactional(isolation = Isolation.SERIALIZABLE)` annotation on `UserService.register()` is the specific line that enables this protection.

**Q4: What does `SameSite=Strict` on a session cookie protect against?**

It protects against **Cross-Site Request Forgery (CSRF)**.

A CSRF attack works by tricking a logged-in user's browser into making a request to your application from a different site — for example, an image tag or form on an attacker's page that submits to `https://yourapp.com/transfer`. The browser automatically attaches cookies to all requests for that domain, so without protection the request arrives with a valid session cookie.

With `SameSite=Strict`, the browser will not attach the session cookie to any request that originates from a different site. The forged request arrives without a session cookie and is treated as unauthenticated.

In this architecture the relevant cookie is `BFF-SESSION` — the server-side session cookie issued by the BFF. The main API itself is stateless and issues no cookies. `BFF-SESSION` is marked `HttpOnly=true` and `SameSite=Strict`, so JavaScript on the page cannot read it and cross-site requests cannot carry it.

`SameSite=Strict` is a defence-in-depth measure. This application also uses a CSRF token (the `XSRF-TOKEN` cookie read by `api.js`) for the same reason. Lab 03 explores CSRF in depth.

**Q5: What HTTP status code should an API return when the user is not authenticated? Why not 403?**

An API should return **401 Unauthorized** when the user is not authenticated.

| Code | Meaning | Use when |
|------|---------|----------|
| 401 | Unauthenticated — we do not know who you are | No valid session or token was provided |
| 403 | Forbidden — we know who you are, but you are not allowed | User is logged in but lacks permission |

Returning 403 for an unauthenticated request is misleading — it tells the client "you are forbidden" when the real problem is "we don't know who you are." A client that receives 401 knows it should prompt the user to log in. A client that receives 403 knows the user is logged in but lacks the required role. In `SecurityConfig.java`:

```java
.defaultAuthenticationEntryPointFor(
    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
    request -> request.getRequestURI().startsWith("/api/")
)
```

Without this, Spring Security's default is to redirect API requests to the login page, returning 302 and breaking API clients that expect JSON.

**Q6: If you removed `UserResponse` and returned `User` directly from `/api/me`, what would be leaked?**

The `User` entity has a `passwordHash` field. Jackson (the JSON serializer) would include every field with a public getter in the response. The `/api/me` response would become:

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "passwordHash": "$argon2id$v=19$m=16384,t=2,p=1$...",
  "role": "ADMIN",
  "createdAt": "2026-05-13T10:00:00Z"
}
```

Even though the value is a hash and not the original password, leaking it is dangerous. An attacker who obtains the hash can run an offline brute-force attack at their own pace, with no rate limiting or account lockout from your server.

`UserResponse` solves this by simply not having a `passwordHash` field. Jackson can only serialize fields that exist on the object it is given. There is no annotation trick required — the data is structurally absent.

**Q7: Why does the `/login` endpoint use `application/x-www-form-urlencoded` instead of JSON?**

The BFF's `SessionController` handles `POST /login` and accepts `application/x-www-form-urlencoded` — the format browsers use when submitting a standard HTML `<form>`. This means the browser can POST the login form directly without any JavaScript involved.

When the BFF receives the form submission it calls `POST /api/auth/token` on the main API, passing the credentials as JSON. The main API validates them, issues a JWT, and returns it. The BFF stores that JWT in the server-side session (keyed under `BFF-SESSION`) and never exposes it to the browser.

This is what makes the BFF pattern work: the browser never sees a JWT. From the browser's perspective it submits a form and receives a session cookie. From the main API's perspective every subsequent request arrives with a valid Bearer token that the BFF extracted from its session and forwarded.

The main API no longer uses Spring Security's `formLogin` at all. It only accepts JWT Bearer tokens and is fully stateless. Any direct API access (curl, Postman, service-to-service) should use `POST /api/auth/token` to obtain a token and then pass it as `Authorization: Bearer <token>`.
