import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import RainfallChart from './RainfallChart';


describe('RainfallChart', () => {
  it('provides an accessible textual summary of chart values', () => {
    render(<RainfallChart monthly={[
      { month: 'January', rainfall_mm: 12.5, valid_years: 30 },
      { month: 'February', rainfall_mm: 9.2, valid_years: 29 },
    ]} />);
    const chart = screen.getByRole('img', { name: /average monthly rainfall in millimetres/i });
    expect(chart).toHaveTextContent('January 12.5 millimetres');
    expect(chart).toHaveTextContent('February 9.2 millimetres');
  });

  it('renders nothing when rainfall evidence is unavailable', () => {
    const { container } = render(<RainfallChart monthly={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
