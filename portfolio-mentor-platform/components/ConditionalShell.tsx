'use client';

import { usePathname } from 'next/navigation';
import { AppShell } from '@/components/AppShell';

/** Overlay route is a separate window — no site header/footer. */
export function ConditionalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const bare = pathname?.startsWith('/interview/overlay');

  if (bare) {
    return <>{children}</>;
  }
  return <AppShell>{children}</AppShell>;
}
