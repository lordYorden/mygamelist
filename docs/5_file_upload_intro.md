## Secure file upload 

## Why file upload is high risk

Uploading means you are accepting **untrusted bytes** that might:

* Execute on the server (dangerous parsers, “polyglot” files, deserialization, malware).
* Get served back to users (stored XSS, content-type confusion).
* Escape storage boundaries (path traversal, overwriting files, symlink tricks).
* Exhaust resources (huge files, zip bombs, too many uploads).
* Poison downstream systems (AV, OCR, PDF/image processing, ML pipelines).

## Core secure principles

* **Treat every upload as hostile.**
* **Validate early, store safely, process later in isolation.**
* **Never trust filename, extension, or client-side checks.**

## Secure controls (server-side)

### 1) Authorization and business rules

* Require auth where appropriate.
* Check *who* can upload *what* for *which object* (prevent IDOR/BOLA).
* Rate limit per user/IP and enforce quotas.

### 2) Size and count limits

* Hard cap request body size.
* Per-file size limit.
* Limit number of files per request.
* Timeouts to stop slow uploads.

### 3) Type validation with allowlist

* Welcomelist **specific formats** (example: only `pdf`, `png`, `jpg`).
* Validate using **magic bytes / file signatures**, not only extension or `Content-Type`.
* If you accept images, prefer **re-encoding** (decode + encode) to strip tricks/metadata.

### 4) Filename and path safety

* Do not use the original filename for storage.
* Generate a random ID filename (UUID) and store the original name as metadata if needed.
* Prevent path traversal 
* Prevent symlink following if writing to disk.

### 5) Safe storage

* Store **outside the web root** (not directly accessible by URL).
* Use a dedicated bucket/container/folder with **least privileges**.
* Disable execute permissions on upload directories.
* Separate public vs private storage.

### 6) Malware scanning and risky format handling

* Scan with AV or cloud malware scanning if your environment supports it.
* Treat risky formats (Office, archives, HTML/SVG) as higher risk or disallow.
* For PDFs and images: avoid “just trust it”, parse in a sandbox if you must.

### 8) Processing architecture

* Prefer: **upload → store raw → queue job → async processing in sandbox → store sanitized version**
* If you generate thumbnails, extract text, parse PDFs: do it in an isolated worker with tight limits.

### 9) Logging and monitoring

* Log upload events (who, size, validated type, storage ID, result).
* Alert on repeated failures, unusual spikes, large files, and suspicious types.

## Recommended “safe-by-default” flow

1. API receives upload, enforces auth + size limits.
2. Reads file stream, checks signature, enforces welcomelist.
3. Saves as `{randomId}` to private storage (no execute, no public URL).
4. (Optional) Malware scan + async processing.
5. Returns only the storage ID. Any later download uses an authorized endpoint.

## Common mistakes to call out

* Relying on extension or browser `Content-Type`.
* Saving with user-provided filename.
* Storing under `/wwwroot/uploads` and serving directly.
* Parsing PDF/Office files synchronously inside the web request.
* No size limits or rate limiting.
* Returning detailed error messages that help attackers tune payloads.


