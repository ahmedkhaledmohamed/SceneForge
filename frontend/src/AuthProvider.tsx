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

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
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
    window.location.href = "/landing/";
  };

  return (
    <AuthContext.Provider value={{ user, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
