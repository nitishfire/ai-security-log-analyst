import { useCallback } from 'react';

/**
 * Returns a `onMouseMove` handler that tracks the cursor position
 * relative to the element and writes --mx / --my CSS custom properties
 * so the radial-gradient glow in index.css can follow the mouse.
 */
export function useMouseGlow() {
  const handleMouseMove = useCallback((e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    e.currentTarget.style.setProperty('--mx', `${x}%`);
    e.currentTarget.style.setProperty('--my', `${y}%`);
  }, []);

  return handleMouseMove;
}
