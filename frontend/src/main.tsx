import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';

const container = document.getElementById('root');
if (!container) throw new Error('no se encontró #root');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
