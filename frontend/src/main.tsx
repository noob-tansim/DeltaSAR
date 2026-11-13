import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import '@fontsource/baloo-da-2/600.css';
import '@fontsource/baloo-da-2/700.css';
import '@fontsource/hind-siliguri/400.css';
import '@fontsource/hind-siliguri/500.css';
import '@fontsource/hind-siliguri/600.css';
import '@fontsource/hind-siliguri/700.css';
import '@fontsource/jetbrains-mono/400.css';
import './styles/base.css';
import './styles/pages.css';
import Story from './pages/Story';
import { WakeBanner } from './components/Chrome';
import { LangProvider } from './lib/i18n';
import { AskWidget } from './components/AskWidget';
import { prewarm } from './lib/api';

const Explore = lazy(() => import('./pages/Explore'));
const Demo = lazy(() => import('./pages/Demo'));
const Methods = lazy(() => import('./pages/Methods'));
const ConsolePage = lazy(() => import('./console/ConsolePage'));
const AppPage = lazy(() => import('./phone/AppPage'));
const JoinDemo = lazy(() => import('./phone/JoinDemo'));

function Loading() {
  return <div style={{ minHeight: '60vh', display: 'grid', placeItems: 'center', color: 'var(--ink-3)' }}>Loading…</div>;
}

function NotFound() {
  return (
    <div style={{ minHeight: '70vh', display: 'grid', placeItems: 'center', textAlign: 'center', padding: 24 }}>
      <div>
        <h1 style={{ fontSize: '2rem' }}>This page is not here.</h1>
        <a className="btn btn-primary" href="/">Back to the story</a>
      </div>
    </div>
  );
}

prewarm();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LangProvider>
    <BrowserRouter>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Story />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/methods" element={<Methods />} />
          <Route path="/console" element={<ConsolePage />} />
          <Route path="/app/*" element={<AppPage />} />
          <Route path="/join/:sid" element={<JoinDemo />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
      <WakeBanner />
      <AskWidget />
    </BrowserRouter>
    </LangProvider>
  </StrictMode>,
);

// Service worker: offline shell for the phone app and Web Push. Registered only in production builds.
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => undefined));
}
