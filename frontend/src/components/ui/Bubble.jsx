import React from 'react';

export default function Bubble({ children, className = '' }) {
  return <div className={`bubble ${className}`}>{children}</div>;
}
