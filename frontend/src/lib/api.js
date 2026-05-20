export async function apiJson(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
    ...options,
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
  return new URLSearchParams({
    username: form.username,
    password: form.password,
  });
}
