# From Zero to SecureTask — Complete Setup Tutorial

This guide walks you through everything needed to get SecureTask running on your machine, starting from a clean Linux or macOS system. Follow each section in order.

---

## What you will end up with

- PostgreSQL running in Docker, holding the application's data
- LocalStack running in Docker, acting as a fake AWS Secrets Manager
- A Spring Boot main API running locally on port 8080, reading its database password from LocalStack
- A Spring Boot BFF (Backend For Frontend) running locally on port 8081, serving the browser UI and proxying API requests
- A working browser UI at http://localhost:8081

---

## Section 1 — Install the required tools

You need four things installed before anything else:

- **Java 21** — the language the app is written in
- **Docker** — runs PostgreSQL and LocalStack as containers
- **Docker Compose** — orchestrates the two containers together
- **Git** — to clone the project (or you can download a zip)

### 1.1 — Install Java 21

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install -y wget apt-transport-https
wget -O - https://packages.adoptium.net/artifactory/api/gpg/key/public | sudo apt-key add -
echo "deb https://packages.adoptium.net/artifactory/deb $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/adoptium.list
sudo apt update
sudo apt install -y temurin-21-jdk
```

**macOS (with Homebrew):**
```bash
brew install --cask temurin@21
```

**Verify:**
```bash
java --version
# Expected: openjdk 21... or similar
```

### 1.2 — Install Docker

**Ubuntu / Debian:**
```bash
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# Log out and back in after this so the group takes effect
```

**macOS:**
Download and install Docker Desktop from https://www.docker.com/products/docker-desktop

**Verify:**
```bash
docker --version
# Expected: Docker version 24.x.x or later

docker compose version
# Expected: Docker Compose version v2.x.x or later
```

> **Why Docker?**
> PostgreSQL and LocalStack each need their own runtime environment. Docker lets you run them in isolated containers without installing them directly on your machine. When you are done you can stop and remove the containers without leaving anything behind on your system.

### 1.3 — Install Git

**Ubuntu / Debian:**
```bash
sudo apt install -y git
```

**macOS:**
```bash
xcode-select --install
```

---

## Section 2 — Understand what the project contains

Before running anything, take a minute to understand the moving parts.

```
SecureTask_Java/
├── settings.gradle               ← Gradle root: declares api and bff as subprojects
├── build.gradle                  ← Plugin version management only
├── gradlew                       ← Gradle wrapper script (runs Gradle without installing it)
├── docker-compose.yml            ← postgres + localstack + api + bff containers
├── localstack/
│   └── init/
│       ├── 01-create-db-secret.sh
│       ├── 02-create-s3-bucket.sh
│       └── 03-create-jwt-secret.sh
├── frontend/                     ← HTML, CSS, JS — served by the BFF
│   ├── login.html
│   ├── dashboard.html
│   ├── css/
│   └── js/
├── api/                          ← Spring Boot REST API (port 8080)
│   ├── build.gradle
│   ├── Dockerfile
│   └── src/main/
│       ├── java/com/securetask/
│       │   ├── config/           ← DB + S3 + JWT config, reads from Secrets Manager
│       │   ├── controller/       ← REST endpoints (/api/register, /api/tasks, …)
│       │   ├── dto/              ← What the API accepts and returns
│       │   ├── entity/           ← JPA entities
│       │   ├── repository/       ← Database queries
│       │   ├── security/         ← JWT Bearer auth, SecurityConfig
│       │   └── service/          ← Business logic
│       └── resources/
│           └── application.properties
└── bff/                          ← Spring Boot BFF (port 8081)
    ├── build.gradle
    ├── Dockerfile
    └── src/main/
        ├── java/com/securetask/bff/
        │   ├── config/           ← SecurityConfig, RestTemplate
        │   ├── controller/       ← SessionController (login/logout), ApiProxyController
        │   └── security/         ← CsrfCookieFilter
        └── resources/
            └── application.properties
```

### Why two containers?

| Container | What it does | Why separate? |
|-----------|-------------|---------------|
| `postgres` | Stores users and tasks in a real SQL database | The app needs persistent, reliable storage |
| `localstack` | Pretends to be AWS Secrets Manager | The app reads its DB password from here, not from a config file |

### Why is the password in Secrets Manager?

Hard-coding a database password in `application.properties` means anyone who can read that file — including anyone who has access to the Git repository — knows the password. Secrets Manager keeps credentials out of the codebase entirely.

In production you would use real AWS Secrets Manager. In local development, LocalStack plays the role of AWS so you do not need an actual AWS account.

---

## Section 3 — Get the project

If you are starting from the files you already have, skip to Section 4.

If you are cloning from a repository:
```bash
git clone <repository-url> SecureTask_Java
cd SecureTask_Java
```

---

## Section 4 — Understand Docker Compose

Open `docker-compose.yml` and read it. There are four services defined:

```yaml
services:
  postgres:    # the database
  localstack:  # the fake AWS
  app:         # the Spring Boot main API on port 8080 (only used for full Docker runs)
  bff:         # the Spring Boot BFF on port 8081 (only used for full Docker runs)
```

For local development you will only start `postgres` and `localstack`. You will run the main API and the BFF directly on your machine using Gradle.

### 4.1 — Start the backing services

```bash
docker compose up -d postgres localstack
```

- `-d` means "detached" — the containers run in the background
- This does not start the `app` or `bff` containers

**What happens next:**

1. Docker pulls the `postgres:16-alpine` image (first time only, ~80 MB)
2. Docker pulls the `localstack/localstack:3.4` image (first time only, ~400 MB)
3. PostgreSQL starts and creates the `securetask` database
4. LocalStack starts and runs the init script

### 4.2 — What the init script does

`localstack/init/01-create-db-secret.sh` runs automatically inside the LocalStack container when it is ready. It calls the LocalStack API to create two secrets:

**Secret: `securetask/db`** (for running the app directly on your machine)
```json
{
  "url": "jdbc:postgresql://localhost:5432/securetask",
  "username": "securetask_user",
  "password": "securetask_password"
}
```

**Secret: `securetask/db-docker`** (for running the app inside Docker)
```json
{
  "url": "jdbc:postgresql://postgres:5432/securetask",
  "username": "securetask_user",
  "password": "securetask_password"
}
```

> **Why two secrets?**
> When the app runs on your machine, `localhost` correctly points to the PostgreSQL container (port 5432 is forwarded). When the app runs inside Docker, `localhost` would point to the app container itself, not PostgreSQL. Inside Docker, containers talk to each other using their service names — so PostgreSQL is reachable at the hostname `postgres`.

### 4.3 — Verify both containers are healthy

```bash
docker compose ps
```

Expected output:
```
NAME                    STATUS
securetask_java-postgres-1      Up (healthy)
securetask_java-localstack-1    Up (healthy)
```

Both must say **healthy** before you start the app. If they say **starting**, wait 10–15 seconds and run the command again.

### 4.4 — Verify the secrets were created

```bash
docker compose logs localstack | grep "is ready"
```

Expected output:
```
Secret 'securetask/db' is ready.
Secret 'securetask/db-docker' is ready.
Secret 'securetask/jwt' is ready.
S3 bucket 'securetask-uploads' is ready.
```

If you do not see those lines, wait a few more seconds and run the command again. If they never appear, check the full log:
```bash
docker compose logs localstack
```

You can also verify the secret contents directly:
```bash
aws --endpoint-url=http://localhost:4566 \
    --region us-east-1 \
    secretsmanager get-secret-value \
    --secret-id securetask/db
```

> **Note:** The `aws` CLI is optional. If you do not have it, the `docker compose logs` check above is sufficient.

---

## Section 5 — Understand how the app reads the secret

Open `api/src/main/java/com/securetask/config/SecretsManagerConfig.java`.

When Spring Boot starts, before it connects to the database, this class runs:

1. It reads five environment variables:
   - `AWS_REGION` — which AWS region to use (LocalStack needs any valid value)
   - `AWS_ACCESS_KEY_ID` — credential (LocalStack accepts anything non-empty)
   - `AWS_SECRET_ACCESS_KEY` — credential (LocalStack accepts anything non-empty)
   - `SECRETS_MANAGER_ENDPOINT` — where to send requests (LocalStack instead of real AWS)
   - `DB_SECRET_NAME` — which secret to fetch

2. It creates an AWS SDK client pointing at `SECRETS_MANAGER_ENDPOINT`

3. It calls `GetSecretValue` to fetch the secret JSON

4. It parses the JSON and extracts `url`, `username`, `password`

5. It builds the database connection pool from those values

If any step fails — wrong endpoint, secret does not exist, malformed JSON — the application refuses to start. There is no fallback to hard-coded credentials.

---

## Section 6 — Run the application

The Gradle wrapper (`./gradlew`) downloads and runs the correct version of Gradle automatically. You do not need to install Gradle separately.

You will need two terminal windows — one for the main API and one for the BFF.

### 6.1 — Terminal 1: Start the main API (first run downloads dependencies)

The first time you run this, Gradle downloads all Java dependencies (~150 MB). Subsequent runs use the cache and are much faster.

```bash
AWS_REGION=us-east-1 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
SECRETS_MANAGER_ENDPOINT=http://localhost:4566 \
DB_SECRET_NAME=securetask/db \
JWT_SECRET_NAME=securetask/jwt \
./gradlew :api:bootRun
```

### 6.2 — What each environment variable means

| Variable | Value | Why |
|----------|-------|-----|
| `AWS_REGION` | `us-east-1` | LocalStack needs a valid region name |
| `AWS_ACCESS_KEY_ID` | `test` | LocalStack does not verify credentials; any non-empty string works |
| `AWS_SECRET_ACCESS_KEY` | `test` | Same as above |
| `SECRETS_MANAGER_ENDPOINT` | `http://localhost:4566` | Redirects AWS SDK calls to LocalStack instead of real AWS |
| `DB_SECRET_NAME` | `securetask/db` | Fetches the secret with `localhost` in the URL (correct for running on your machine) |
| `JWT_SECRET_NAME` | `securetask/jwt` | Fetches the JWT signing key secret |

### 6.3 — Terminal 2: Start the BFF

In a second terminal, run:

```bash
./gradlew :bff:bootRun
```

> **Note:** The BFF needs no environment variables for local development. It defaults to connecting to the main API at `http://localhost:8080` and serves the frontend files from the `frontend/` directory.

### 6.4 — What a successful startup looks like

For the main API:
```
  .   ____          _            __ _ _
 /\\ / ___'_ __ _ _(_)_ __  __ _ \ \ \ \
( ( )\___ | '_ | '_| | '_ \/ _` | \ \ \ \
 \\/  ___)| |_)| | | | | || (_| |  ) ) ) )
  '  |____| .__|_| |_|_| |_\__, | / / / /
 =========|_|==============|___/=/_/_/_/
 :: Spring Boot ::                (v3.3.2)

...
Started SecureTaskApplication in 4.2 seconds
```

The BFF will print a similar banner and report that it started on port 8081.

### 6.5 — What a failed startup looks like and why

**"Unknown host: postgres"**
You used `DB_SECRET_NAME=securetask/db-docker` (Docker hostname) while running on your machine. Use `securetask/db` instead.

**"Connection refused" on port 4566**
LocalStack is not running or not yet healthy. Run `docker compose ps` and wait for it to show `healthy`.

**"Secret not found"**
The init script has not run yet or failed. Check `docker compose logs localstack`.

**"Connection refused" on port 5432**
PostgreSQL is not running. Run `docker compose up -d postgres`.

---

## Section 7 — Open the application in your browser

With both services running, open: **http://localhost:8081**

All browser traffic goes through the BFF on port 8081. The main API on port 8080 is for direct programmatic access (curl, Postman) using JWT Bearer tokens.

### 7.1 — Register the first user (becomes ADMIN)

1. Click **Register**
2. Fill in username, email, and password (password must be at least 8 characters)
3. Click **Register**
4. You are redirected to the login page

### 7.2 — Log in

1. Enter your username and password
2. Click **Log in**
3. You land on the dashboard

### 7.3 — Inspect the dashboard

The dashboard shows:
- Your username
- Your email
- Your role — the first registered user always gets **ADMIN**
- When your account was created

### 7.4 — Register a second user (becomes VIEWER)

Open an incognito/private window and go to http://localhost:8081/register.html. Register a different account. When you log in with it, the role will be **VIEWER**.

### 7.5 — Try accessing a protected page without logging in

Open http://localhost:8081/dashboard.html in a new tab where you are not logged in. The BFF returns 401. The API behaves the same way — try:

```bash
curl -i http://localhost:8080/api/me
```

Expected:
```
HTTP/1.1 401
```

---

## Section 8 — Run the tests

The tests use **Testcontainers**, which automatically starts a real PostgreSQL container just for the test run. You do not need LocalStack running for the tests.

Docker must be running (so Testcontainers can start the container):
```bash
./gradlew :api:test
```

Expected output:
```
> Task :api:test

UserServiceTest > firstUserBecomesAdmin() PASSED
...
AuthControllerTest > registrationReturns201WithSafeFields() PASSED
...
AdminControllerTest > listUsers_asAdmin_returns200() PASSED
...
TaskControllerTest > createTask_returnsCreated() PASSED
...
WebhookControllerTest > createWebhook_validUrl_returns201() PASSED
...
SsrfGuardTest > allowsPublicHttpsUrl() PASSED
...
AttachmentControllerTest > uploadAttachment_validPng_returns201() PASSED
...
FileTypeValidatorTest > pngMagicBytesAccepted() PASSED
...
TokenControllerTest > issueToken_validCredentials_returns200() PASSED
...
MassAssignmentTest > createTask_pinnedInBody_isIgnored() PASSED
...

BUILD SUCCESSFUL
```

---

## Section 9 — Stop everything

Stop the Spring Boot apps: press `Ctrl+C` in each terminal where they are running.

Stop the Docker containers:
```bash
docker compose down
```

This stops and removes the containers but keeps the database data in a Docker volume. Next time you run `docker compose up -d postgres localstack` your data will still be there.

To also delete the data:
```bash
docker compose down -v
```

---

## Section 10 — Common questions

**Do I need an AWS account?**
No. LocalStack emulates AWS Secrets Manager locally. No AWS account, no credit card, no internet requests to AWS.

**Why not just put the password in application.properties?**
Because `application.properties` is typically committed to version control. Anyone with access to the repository would have the database password. Secrets Manager keeps credentials out of the codebase entirely — this is a core principle of the [12-factor app](https://12factor.net/config).

**Why Argon2 and not BCrypt?**
BCrypt was designed in 1999. Argon2 won the Password Hashing Competition in 2015 and is specifically designed to be resistant to GPU and ASIC-based attacks. It uses significantly more memory per hash, which makes parallel brute-force attacks much more expensive.

**Why does the first user become ADMIN?**
This avoids hard-coded admin credentials in configuration or code. There is no default password to discover, no `admin/admin` to change. The first person to set up the system naturally becomes the administrator.

**What if two people register at exactly the same moment?**
The registration uses `SERIALIZABLE` database transaction isolation. PostgreSQL's Serializable Snapshot Isolation (SSI) detects when two transactions would create a conflict — like both observing an empty users table — and aborts one of them. Only one person becomes ADMIN.

---

## Summary of commands

```bash
# Start backing services
docker compose up -d postgres localstack

# Verify they are healthy
docker compose ps

# Verify secrets were created
docker compose logs localstack | grep "is ready"

# Run the main API (Terminal 1)
AWS_REGION=us-east-1 \
AWS_ACCESS_KEY_ID=test \
AWS_SECRET_ACCESS_KEY=test \
SECRETS_MANAGER_ENDPOINT=http://localhost:4566 \
DB_SECRET_NAME=securetask/db \
JWT_SECRET_NAME=securetask/jwt \
./gradlew :api:bootRun

# Run the BFF (Terminal 2)
./gradlew :bff:bootRun

# Run tests (no LocalStack needed)
./gradlew :api:test

# Stop containers
docker compose down

# Stop containers and delete data
docker compose down -v
```

---

## Next step

Continue to [Lab 01 — Authentication](01-authentication.md) to understand what was built, inspect the security decisions in the code, and answer the lab questions.
