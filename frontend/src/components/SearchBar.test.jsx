import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '../api';
import SearchBar from './SearchBar';


vi.mock('../api', () => ({
  api: { get: vi.fn() },
  apiErrorMessage: vi.fn(() => 'Place search failed.'),
}));


describe('SearchBar', () => {
  beforeEach(() => {
    api.get.mockResolvedValue({
      data: [{ display_name: 'Ralegan Siddhi, Maharashtra, India', lat: 19.36, lng: 74.45 }],
    });
  });

  it('waits for explicit submission and lets the user select a result', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SearchBar onSelect={onSelect} />);

    await user.type(screen.getByRole('searchbox', { name: /village or location/i }), 'Ralegan Siddhi');
    expect(api.get).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    expect(api.get).toHaveBeenCalledWith('/search-village', expect.objectContaining({
      params: { q: 'Ralegan Siddhi' },
    }));

    await user.click(screen.getByRole('button', { name: /Ralegan Siddhi, Maharashtra/i }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ lat: 19.36, lng: 74.45 }));
  });

  it('rejects a one-character query without calling the API', async () => {
    const user = userEvent.setup();
    render(<SearchBar onSelect={vi.fn()} />);
    await user.type(screen.getByRole('searchbox'), 'x');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(api.get).not.toHaveBeenCalled();
    expect(screen.getByText('Enter at least two characters.')).toBeInTheDocument();
  });
});
