import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import App from './App';

// Simple check
describe('App Component', () => {
  it('renders without crashing', () => {
    const { container } = render(
        <App />
    );
    expect(container).toBeTruthy();
  });
});
