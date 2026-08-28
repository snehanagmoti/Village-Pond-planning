import axios from 'axios';

const baseURL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
export const DEFAULT_API_TIMEOUT_MS = 60000;
export const MAX_API_TIMEOUT_MS = 300000;

export function normalizeApiTimeout(value) {
  const configuredTimeout = Number(value);
  return Number.isFinite(configuredTimeout) && configuredTimeout >= 1000
    ? Math.min(configuredTimeout, MAX_API_TIMEOUT_MS)
    : DEFAULT_API_TIMEOUT_MS;
}

const timeout = normalizeApiTimeout(import.meta.env.VITE_API_TIMEOUT_MS || DEFAULT_API_TIMEOUT_MS);

export const api = axios.create({
  baseURL,
  timeout,
  headers: { Accept: 'application/json' },
});

export function apiErrorMessage(error, fallback = 'The request could not be completed.') {
  if (axios.isCancel(error) || error?.code === 'ERR_CANCELED') return 'Request cancelled.';
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join('; ');
  if (error?.code === 'ECONNABORTED') return 'The request timed out. Please try again.';
  return fallback;
}
