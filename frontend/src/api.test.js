import { describe, expect, it } from 'vitest';

import {
  DEFAULT_API_TIMEOUT_MS,
  MAX_API_TIMEOUT_MS,
  normalizeApiTimeout,
} from './api';

describe('normalizeApiTimeout', () => {
  it('preserves the five-minute production timeout', () => {
    expect(normalizeApiTimeout(300000)).toBe(300000);
    expect(normalizeApiTimeout('180000')).toBe(180000);
  });

  it('uses safe bounds for invalid or excessive values', () => {
    expect(normalizeApiTimeout('invalid')).toBe(DEFAULT_API_TIMEOUT_MS);
    expect(normalizeApiTimeout(999)).toBe(DEFAULT_API_TIMEOUT_MS);
    expect(normalizeApiTimeout(900000)).toBe(MAX_API_TIMEOUT_MS);
  });
});
