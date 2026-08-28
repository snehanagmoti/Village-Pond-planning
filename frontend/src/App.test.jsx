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
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  Marker: ({ children }) => <div>{children}</div>,
  Polygon: ({ children }) => <div>{children}</div>,
  Polyline: ({ children }) => <div>{children}</div>,
  Popup: ({ children }) => <div>{children}</div>,
  TileLayer: () => null,
  Tooltip: ({ children }) => <div>{children}</div>,
  useMap: () => ({ flyTo: vi.fn() }),
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
      analysis_status: 'degraded',
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
        selection_method: 'Maximum D8 contributing area',
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
      study_area_boundary: [
        { lat: 21.22, lng: 81.27 },
        { lat: 21.25, lng: 81.29 },
        { lat: 21.22, lng: 81.31 },
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
  expect(config.signal).toBeInstanceOf(AbortSignal);
  expect(await screen.findByRole('heading', { name: 'Contour-derived pond candidate' })).toBeInTheDocument();
  expect(screen.getByText('392.1225 ha')).toBeInTheDocument();
  expect(screen.getByText('Interpolated surface; field verification required.')).toBeInTheDocument();
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
