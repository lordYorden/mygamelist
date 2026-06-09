export async function apiJson(path, options = {}) {
  const { headers: optionHeaders, ...fetchOptions } = options;
  const method = (fetchOptions.method || "GET").toUpperCase();
  const unsafe = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  const token = unsafe ? getCsrfToken() : null;

  const response = await fetch(path, {
    ...fetchOptions,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(fetchOptions.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(unsafe && token ? { "X-XSRF-TOKEN": token } : {}),
      ...optionHeaders,
    },
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(formatApiError(data));
  }
  return data;
}

function formatApiError(data) {
  const detail = data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map(formatValidationIssue).join("\n");
  }

  if (detail && typeof detail === "object") {
    return detail.message || JSON.stringify(detail);
  }

  return data?.message || "Request failed";
}

function getCookie(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function getCsrfToken() {
  return getCookie("XSRF-TOKEN");
}

function formatValidationIssue(issue) {
  if (typeof issue === "string") {
    return issue;
  }

  const location = Array.isArray(issue?.loc)
    ? issue.loc.filter((part) => part !== "body").join(".")
    : "";
  const message = issue?.msg || "Invalid value";

  return location ? `${humanizeField(location)}: ${message}` : message;
}

function humanizeField(value) {
  return value
    .replaceAll("_", " ")
    .replaceAll(".", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function loginBody(form) {
  const params = new URLSearchParams({
    username: form.username,
    password: form.password,
  });

  const token = getCsrfToken();
  if (token) {
    params.append("_csrf", token);
  }

  return params;
}
