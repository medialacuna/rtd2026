import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './styles.css';
import { I18nProvider } from './i18n/i18n';
import { AuthProvider } from './hooks/useAuth';
import Layout from './components/Layout';
import Join from './pages/Join';
import Pool from './pages/Pool';
import Muar from './pages/Muar';
import Scene from './pages/Scene';
import Acts from './pages/Acts';
import Plays from './pages/Plays';
import AiLog from './pages/Ai';
import Me from './pages/Me';
import Stage from './pages/Stage';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Join />} />
              <Route path="/verify" element={<Join />} />
              <Route path="/pool" element={<Pool />} />
              <Route path="/muar" element={<Muar />} />
              <Route path="/scene" element={<Scene />} />
              <Route path="/act" element={<Acts />} />
              <Route path="/plays" element={<Plays />} />
              <Route path="/ai" element={<AiLog />} />
              <Route path="/me" element={<Me />} />
              <Route path="/stage" element={<Stage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  </React.StrictMode>,
);
