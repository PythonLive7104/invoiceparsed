import axios from "axios";

// VITE_API_URL set to "" → same-origin (nginx proxies /api to the backend in
// the Docker deploy). Unset (dev) → talk to the local Flask server directly.
const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:5000";

const TOKEN_KEY = "ia_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export const api = axios.create({ baseURL: BASE_URL });

// Attach the JWT to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Normalize axios errors into a readable message. */
export function apiError(err, fallback = "Something went wrong.") {
  return err?.response?.data?.error || err?.message || fallback;
}

/** Download a file from an authenticated endpoint as a browser download. */
export async function downloadFile(path, filename) {
  const res = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
