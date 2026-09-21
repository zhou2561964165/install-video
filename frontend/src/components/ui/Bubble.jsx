import React from 'react';

export default function Bubble({ children, className = '' }) {
  return <div className={`bubble laser-frame ${className}`}>{children}</div>;
}
