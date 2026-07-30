import { createContext, useContext, useEffect, useState } from "react";
import { getAuthToken, setAuthToken } from "./api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  avatar_url: string;
  provider: string;
}

export type UserPreferences = Record<string, string>;

interface AuthContextType {
  user: AuthUser | null;
  preferences: UserPreferences;
  loading: boolean;
  logout: () => void;
  updatePreferences: (prefs: Partial<UserPreferences>) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  preferences: {},
  loading: true,
  logout: () => {},
  updatePreferences: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [preferences, setPreferences] = useState<UserPreferences>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      setAuthToken(urlToken);
      window.history.replaceState({}, "", window.location.pathname);
    }

    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      return;
    }

    fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.user) {
          setUser(data.user);
          setPreferences(data.preferences ?? {});
        } else {
          setAuthToken(null);
        }
      })
      .catch(() => setAuthToken(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    const token = getAuthToken();
    if (token) {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
    }
    setAuthToken(null);
    setUser(null);
    setPreferences({});
    window.location.href = "/landing/";
  };

  const updatePreferences = async (prefs: Partial<UserPreferences>) => {
    const token = getAuthToken();
    if (!token) return;
    try {
      const r = await fetch(`${API_BASE}/auth/preferences`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(prefs),
      });
      if (r.ok) {
        const updated = await r.json();
        setPreferences(updated);
      }
    } catch { /* silent */ }
  };

  return (
    <AuthContext.Provider value={{ user, preferences, loading, logout, updatePreferences }}>
      {children}
    </AuthContext.Provider>
  );
}
