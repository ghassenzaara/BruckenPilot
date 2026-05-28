import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Theme = 'light' | 'dark' | 'system';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  resolved: 'light' | 'dark';
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark',
  setTheme: () => {},
  resolved: 'dark',
});

const STORAGE_KEY = 'brueckenpilot-theme';

function systemPrefersDark() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem(STORAGE_KEY) as Theme) || 'dark',
  );
  const [resolved, setResolved] = useState<'light' | 'dark'>('dark');

  useEffect(() => {
    const apply = () => {
      const isDark = theme === 'dark' || (theme === 'system' && systemPrefersDark());
      document.documentElement.classList.toggle('dark', isDark);
      setResolved(isDark ? 'dark' : 'light');
    };
    apply();
    localStorage.setItem(STORAGE_KEY, theme);

    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      mq.addEventListener('change', apply);
      return () => mq.removeEventListener('change', apply);
    }
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolved }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const useTheme = () => useContext(ThemeContext);
