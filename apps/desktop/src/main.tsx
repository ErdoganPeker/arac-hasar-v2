/**
 * App entry — wires i18n, providers (Theme, Auth), router, and applies any
 * persisted settings (apiUrl / apiKey / language) before mounting React.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import '@arac-hasar/ui/styles';
import './styles.css';
import './i18n';
import { detectOsLanguage, setLanguage } from './i18n';
import { loadSettings } from './lib/settings';
import { api } from './lib/api';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { applyTheme } from './lib/theme';

// Apply persisted settings BEFORE first render so axios baseURL is correct and
// the UI never flashes the wrong language/theme.
async function bootstrap() {
  try {
    const settings = await loadSettings();
    api.setBaseUrl(settings.apiUrl);
    api.setApiKey(settings.apiKey);
    applyTheme(settings.theme);
    const osLang = await detectOsLanguage();
    await setLanguage(settings.uiLanguage ?? osLang ?? 'tr');
  } catch (e) {
    console.warn('Bootstrap failed (continuing with defaults):', e);
  }

  const rootElement = document.getElementById('root');
  if (!rootElement) throw new Error('Root element not found');

  createRoot(rootElement).render(
    <StrictMode>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </StrictMode>,
  );
}

void bootstrap();
