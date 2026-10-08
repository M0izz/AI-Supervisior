import React, { StrictMode, useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import { FloatingHud } from './components/FloatingHud.tsx';

const RootRouter: React.FC = () => {
  const [isHud, setIsHud] = useState<boolean>(() => {
    return (
      window.location.hash === '#hud' ||
      window.location.search.includes('view=hud') ||
      window.location.search.includes('window=hud')
    );
  });

  useEffect(() => {
    const handleHashChange = () => {
      setIsHud(
        window.location.hash === '#hud' ||
        window.location.search.includes('view=hud') ||
        window.location.search.includes('window=hud')
      );
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  if (isHud) {
    return <FloatingHud />;
  }

  return <App />;
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RootRouter />
  </StrictMode>,
);
