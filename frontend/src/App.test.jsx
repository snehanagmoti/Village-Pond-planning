import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { api } from './api';
import App from './App';


vi.mock('./api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
  apiErrorMessage: vi.fn(() => 'Request failed.'),
}));

vi.mock('leaflet', () => ({
  default: {
    icon: vi.fn(() => ({})),
    divIcon: vi.fn(() => ({})),
    Marker: { prototype: { options: {} } },
  },
}));

vi.mock('leaflet/dist/images/marker-icon.png', () => ({ default: '' }));
vi.mock('leaflet/dist/images/marker-shadow.png', () => ({ default: '' }));

vi.mock('react-leaflet', () => ({
  Circle: ({ children }) => <div>{children}</div>,
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  Marker: ({ children }) => <div>{children}</div>,
  Polygon: ({ children }) => <div>{children}</div>,
  Polyline: ({ children }) => <div>{children}</div>,
  Popup: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Tooltip: ({ children }) => <div>{children}</div>,
  useMap: () => ({ flyTo: vi.fn(), fitBounds: vi.fn(), invalidateSize: vi.fn() }),
  useMapEvents: vi.fn(),
}));


it('requires explicit confirmation after coordinates are selected', async () => {
  api.post.mockReturnValue(new Promise(() => {}));
  const user = userEvent.setup();
  render(<App />);

  await user.type(screen.getByRole('spinbutton', { name: 'Latitude' }), '18.5204');
  await user.type(screen.getByRole('spinbutton', { name: 'Longitude' }), '73.8567');
  await user.click(screen.getByRole('button', { name: 'Select coordinates' }));
  expect(api.post).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Start screening analysis' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  expect(api.post).toHaveBeenCalledWith('/analyze', expect.objectContaining({
    center: { lat: 18.5204, lng: 73.8567 },
    radius_km: 2,
  }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
});


it('uploads a KML contour map and renders its derived catchment result', async () => {
  api.post.mockResolvedValue({
    data: {
      analysis_status: 'complete',
      input_file: 'terrain.kml',
      input_format: 'kml',
      contour_summary: {
        contour_count: 5,
        source_point_count: 25,
        elevation_level_count: 5,
        minimum_elevation_m: 270,
        maximum_elevation_m: 274,
        median_contour_interval_m: 1,
      },
      grid: {
        rows: 20,
        columns: 24,
        cell_size_m: 18,
        observed_cell_ratio: 0.2,
        interpolation_iterations: 30,
        interpolation_converged: true,
        method: 'Contour rasterization with harmonic interpolation',
      },
      pond_location: {
        lat: 21.2398,
        lng: 81.2864,
        elevation_m: 271.3,
        boundary_distance_m: 90,
        local_slope_percent: 2.1,
        suitability_score: 87.5,
        contributing_area_sqm: 3921225,
        water_distance_m: 140,
        selection_method: 'Highest interior D8 contributing area',
      },
      candidate_options: [
        {
          rank: 1, lat: 21.2398, lng: 81.2864, elevation_m: 271.3,
          boundary_distance_m: 90, local_slope_percent: 2.1,
          suitability_score: 87.5, contributing_area_hectares: 392.1225,
          water_distance_m: 140, selected: true, selection_reason: 'Best terrain score',
        },
        {
          rank: 2, lat: 21.2410, lng: 81.2880, elevation_m: 272.0,
          boundary_distance_m: 120, local_slope_percent: 3.2,
          suitability_score: 78.0, contributing_area_hectares: 250.0,
          water_distance_m: 180, selected: false, selection_reason: 'Alternative',
        },
      ],
      selection: { mode: 'automatic', requested_point: null, requested_region: [], snapped_distance_m: null },
      outlet_location: {
        lat: 21.2390,
        lng: 81.2864,
        elevation_m: 270.9,
        contributing_cells: 12103,
      },
      catchment: {
        area_sqm: 3921225,
        area_hectares: 392.1225,
        cell_count: 12102,
        study_grid_fraction: 0.55,
        boundary: [
          { lat: 21.23, lng: 81.28 },
          { lat: 21.24, lng: 81.29 },
          { lat: 21.22, lng: 81.30 },
        ],
      },
      rainfall_data: { annual_avg_mm: 900, valid_years: 30, monthly: [] },
      runoff_stats: {
        catchment_area_sqm: 3921225,
        annual_rainfall_mm: 900,
        runoff_coefficient: 0.3,
        runoff_coefficient_basis: 'Course demo scenario',
        estimated_volume_m3: 1058730.75,
      },
      pond: null,
      eligible_candidate_area_sqm: 100000,
      water_screening: {
        status: 'applied', method: 'RGB/HSV satellite water classification',
        detected_water_ratio: 0.04, exclusion_buffer_m: 60,
        message: 'Detected water is excluded; field verification remains required.',
      },
      study_area_boundary: [
        { lat: 21.22, lng: 81.27 },
        { lat: 21.25, lng: 81.29 },
        { lat: 21.22, lng: 81.31 },
      ],
      study_boundary_source: 'uploaded_polygon',
      candidate_boundary_setback_m: 75,
      contours: [
        { elevation: 271, points: [{ lat: 21.22, lng: 81.27 }, { lat: 21.23, lng: 81.28 }, { lat: 21.24, lng: 81.27 }] },
      ],
      drainage_path: [
        { lat: 21.2398, lng: 81.2864 },
        { lat: 21.2390, lng: 81.2864 },
      ],
      quality: {
        status: 'degraded',
        screening_only: true,
        sources: {
          contours: { name: 'Uploaded contour map', status: 'degraded', retrieved_at: '2026-08-26T00:00:00Z' },
        },
        warnings: ['Interpolated surface; field verification required.'],
      },
    },
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole('tab', { name: 'Contour upload' }));
  const file = new File(['<kml />'], 'terrain.kml', { type: 'application/vnd.google-earth.kml+xml' });
  await user.upload(screen.getByLabelText('Contour file'), file);
  await user.click(screen.getByRole('button', { name: 'Analyze contour map' }));

  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  const [path, body, config] = api.post.mock.calls[0];
  expect(path).toBe('/analyze-contour');
  expect(body).toBeInstanceOf(FormData);
  expect(body.get('contour_file')).toBe(file);
  expect(body.get('selection_mode')).toBe('automatic');
  expect(config.signal).toBeInstanceOf(AbortSignal);
  expect(await screen.findByRole('heading', { name: 'Contour analysis complete' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Selected pond screening result' })).toBeInTheDocument();
  expect(screen.getByText('Contour data notes')).toBeInTheDocument();
  expect(screen.queryByText('Limitations and warnings')).not.toBeInTheDocument();
  expect(screen.getByText('392.1225 ha')).toBeInTheDocument();
  expect(screen.getByText('Estimated runoff volume')).toBeInTheDocument();
  expect(screen.getByText((content) => content.replaceAll(',', '').includes('1058731 m³/year'))).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Use this option and recompute' })).toBeInTheDocument();
  expect(screen.getByText('Interpolated surface; field verification required.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /DEM surface \+ elevation contours/ })).toHaveAttribute('aria-pressed', 'true');

  await user.click(screen.getByRole('button', { name: 'Use this option and recompute' }));
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
  const manualBody = api.post.mock.calls[1][1];
  expect(manualBody.get('selection_mode')).toBe('point');
  expect(manualBody.get('selected_lat')).toBe('21.241');
  expect(manualBody.get('selected_lng')).toBe('81.288');
});


test('collapses and restores the analysis panel without removing the map', async () => {
  const user = userEvent.setup();
  render(<App />);

  const toggle = screen.getByRole('button', { name: 'Hide panel' });
  const panel = screen.getByRole('complementary', { name: 'Pond screening controls and results' });
  expect(toggle).toHaveAttribute('aria-expanded', 'true');

  await user.click(toggle);

  expect(screen.getByTestId('map')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Show panel' })).toHaveAttribute('aria-expanded', 'false');
  expect(panel).toHaveAttribute('aria-hidden', 'true');

  await user.click(screen.getByRole('button', { name: 'Show panel' }));
  expect(screen.getByRole('button', { name: 'Hide panel' })).toHaveAttribute('aria-expanded', 'true');
});

test('switches between the live analysis and contour upload workflows', async () => {
  const user = userEvent.setup();
  render(<App />);

  const liveTab = screen.getByRole('tab', { name: 'Live analysis' });
  const contourTab = screen.getByRole('tab', { name: 'Contour upload' });

  expect(liveTab).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByLabelText('Latitude')).toBeInTheDocument();
  expect(screen.queryByLabelText('Contour file')).not.toBeInTheDocument();

  await user.click(contourTab);

  expect(contourTab).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByLabelText('Contour file')).toBeInTheDocument();
  expect(screen.queryByLabelText('Latitude')).not.toBeInTheDocument();
  expect(screen.getByText('Select a KML or KMZ contour map to start the file-based analysis.')).toBeInTheDocument();

  await user.click(liveTab);

  expect(liveTab).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByLabelText('Latitude')).toBeInTheDocument();
  expect(screen.getByText('Select a location, review the radius, then start the screening analysis.')).toBeInTheDocument();
});
