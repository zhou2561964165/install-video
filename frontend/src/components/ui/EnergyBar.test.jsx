import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import EnergyBar from './EnergyBar.jsx';

describe('EnergyBar', () => {
  it('clamps value to 0..100 and sets aria', () => {
    const { rerender } = render(<EnergyBar value={150} />);
    expect(document.querySelector('[role="progressbar"]')).toHaveAttribute('aria-valuenow', '100');
    rerender(<EnergyBar value={-5} />);
    expect(document.querySelector('[role="progressbar"]')).toHaveAttribute('aria-valuenow', '0');
  });
});
