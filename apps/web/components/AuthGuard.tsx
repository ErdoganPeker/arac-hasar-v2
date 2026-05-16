'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Spinner } from '@arac-hasar/ui';
import { useAuth } from '@/lib/auth-context';

interface AuthGuardProps {
  children: React.ReactNode;
  /** Require admin role. */
  requireAdmin?: boolean;
  fallback?: React.ReactNode;
}

/**
 * Client-side guard for protected pages. Middleware already redirects
 * unauthenticated users at the edge — this is the in-app belt + suspenders
 * for hydration / SPA navigation cases.
 */
export function AuthGuard({
  children,
  requireAdmin = false,
  fallback,
}: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isAdmin, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) {
      const next = encodeURIComponent(pathname ?? '/');
      router.replace(`/login?next=${next}`);
      return;
    }
    if (requireAdmin && !isAdmin) {
      router.replace('/dashboard?error=forbidden');
    }
  }, [loading, isAuthenticated, isAdmin, requireAdmin, router, pathname]);

  if (loading || !isAuthenticated || (requireAdmin && !isAdmin)) {
    return (
      fallback ?? (
        <div className="flex min-h-[40vh] items-center justify-center">
          <Spinner size="lg" />
        </div>
      )
    );
  }
  return <>{children}</>;
}
