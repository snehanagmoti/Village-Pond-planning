import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import MapResultSummary from './MapResultSummary';

it('distinguishes annual runoff from storage on the live map', () => {
  render(<MapResultSummary result={{ runoff_stats: { catchment_area_sqm: 10000, estimated_volume_m3: 2400 }, pond: { lat: 21, lng: 81, capacity_m3: 1920 } }} />);
  expect(screen.getByRole('region', { name: 'Mapped analysis results' })).toBeInTheDocument();
  expect(screen.getByText('2,400 m³/year')).toBeInTheDocument();
  expect(screen.getByText('1,920 m³')).toBeInTheDocument();
  expect(screen.getByText('1 ha')).toBeInTheDocument();
});

it('uses contour catchment and does not invent missing storage', () => {
  render(<MapResultSummary contour result={{ catchment: { area_sqm: 20000 }, runoff_stats: { estimated_volume_m3: 0 } }} />);
  expect(screen.getByText('2 ha')).toBeInTheDocument();
  expect(screen.getByText('0 m³/year')).toBeInTheDocument();
  expect(screen.getByText('Unavailable m³')).toBeInTheDocument();
  expect(screen.getByText('No valid pond recommendation')).toBeInTheDocument();
});
