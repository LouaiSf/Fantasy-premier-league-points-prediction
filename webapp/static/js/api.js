export async function requestJson(path, options = undefined) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({ ok: false, error: "The server returned an unreadable response." }));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed with status ${response.status}.`);
  }
  return payload;
}

export function postJson(path, body) {
  return requestJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function money(value) {
  return hasNumericValue(value) ? `£${Number(value).toFixed(1)}m` : "--";
}

export function number(value, digits = 1) {
  return hasNumericValue(value) ? Number(value).toFixed(digits) : "--";
}

export function signed(value) {
  if (!hasNumericValue(value)) return "--";
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : numeric < 0 ? "−" : ""}${Math.abs(numeric).toFixed(1)}`;
}

function hasNumericValue(value) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;",
  })[character]);
}
