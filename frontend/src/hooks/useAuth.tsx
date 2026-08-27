import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { auth, type User } from "@/lib/api";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isSuperadmin: boolean;
  isAdmin: boolean;
  can: (permission: string) => boolean;
  canAny: (permissions: string[]) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

export function checkPermission(user: User | null, requiredPerm: string): boolean {
  if (!user) return false;
  if (user.is_superadmin || user.role === "superadmin") return true;
  const perms = user.permissions || [];
  if (perms.includes("*") || perms.includes("system:admin")) return true;
  if (perms.includes(requiredPerm)) return true;
  if (requiredPerm.includes(":")) {
    const scope = requiredPerm.split(":")[0];
    if (perms.includes(`${scope}:*`)) return true;
  }
  return false;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!auth.isAuthenticated()) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const me = await auth.me();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    await auth.login(email, password);
    await refreshUser();
  }, [refreshUser]);

  const logout = useCallback(async () => {
    await auth.logout();
    setUser(null);
  }, []);

  const can = useCallback((permission: string) => {
    return checkPermission(user, permission);
  }, [user]);

  const canAny = useCallback((permissions: string[]) => {
    if (!user) return false;
    if (user.is_superadmin || user.role === "superadmin") return true;
    return permissions.some((p) => checkPermission(user, p));
  }, [user]);

  const isSuperadmin = !!user && (user.is_superadmin || user.role === "superadmin");
  const isAdmin = isSuperadmin || (!!user && (user.role === "admin" || can("system:admin")));

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        isSuperadmin,
        isAdmin,
        can,
        canAny,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
