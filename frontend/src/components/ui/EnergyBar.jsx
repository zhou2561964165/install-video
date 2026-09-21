import React from 'react';

export default function EnergyBar({ value }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} className="energy-bar">
      <div className="energy-bar-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}
