const TOKEN_KEY = "statements.token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(method, path, body, isForm = false) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let payload = body;
  if (body && !isForm) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(`/api${path}`, { method, headers, body: payload });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("statements:logout"));
    throw new Error("Session expired. Please log in again.");
  }
  if (res.status === 204) return null;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b),
  put: (p, b) => request("PUT", p, b),
  patch: (p, b) => request("PATCH", p, b),
  del: (p) => request("DELETE", p),
  postForm: (p, formData) => request("POST", p, formData, true),
};

async function downloadBlob(url, filename) {
  const token = getToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename || "document";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

/** Fetch a document as a blob (with auth) and trigger a browser download. */
export async function downloadDocument(id, filename) {
  await downloadBlob(`/api/documents/${id}/download`, filename);
}

/** Download any file inside the documents root by its relative path. */
export async function downloadFile(path, filename) {
  await downloadBlob(`/api/files/download?path=${encodeURIComponent(path)}`, filename);
}

/** Download the travel-report xlsx for a person in a given month. */
export async function downloadTravelReport(periodId, name) {
  await downloadBlob(
    `/api/periods/${periodId}/travels/export?name=${encodeURIComponent(name)}`,
    `Cestovne_${name}.xlsx`
  );
}

/** Download the Kniha jázd xlsx for a vehicle and month. */
export async function downloadLogbook(vehicleId, year, month, ecv) {
  const mm = String(month).padStart(2, "0");
  await downloadBlob(
    `/api/vehicles/${vehicleId}/trips/export?year=${year}&month=${month}`,
    `Kniha_jazd_${ecv}_${year}_${mm}.xlsx`
  );
}
