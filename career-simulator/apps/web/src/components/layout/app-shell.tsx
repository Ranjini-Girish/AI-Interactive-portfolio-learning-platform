'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Briefcase, FileText, LayoutDashboard, LogIn, LogOut, Mic, Route, Sparkles, Target, User } from 'lucide-react';
import { MentorSidebar, MentorMobileFab } from '@/components/layout/mentor-sidebar';
import { ThemeToggle } from '@/components/layout/theme-toggle';
import { useAuth } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const nav = [
  { href: '/', label: 'Home', icon: LayoutDashboard },
  { href: '/dashboard', label: 'Dashboard', icon: User, auth: true },
  { href: '/resume', label: 'Resume', icon: FileText, auth: true },
  { href: '/job', label: 'Job match', icon: Target, auth: true },
  { href: '/journey', label: 'Your journey', icon: Route },
  { href: '/roles', label: 'Job simulations', icon: Briefcase },
  { href: '/portfolio', label: 'Portfolio', icon: Sparkles, auth: true },
  { href: '/interview', label: 'Interview', icon: Mic, auth: true },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();

  const isAuthPage = pathname === '/login' || pathname === '/register';

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
              CT
            </span>
            <span className="hidden font-semibold sm:inline">Career Transition Simulator</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            {nav.map(({ href, label, icon: Icon, auth }) => {
              if (auth && !user) return null;
              const active = pathname === href || (href !== '/' && pathname.startsWith(href));
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-2 ${
                    active
                      ? 'bg-accent text-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden md:inline">{label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="hidden sm:inline-flex">
              Phase 10
            </Badge>
            {!loading && !user && !isAuthPage && (
              <Button asChild size="sm" variant="outline">
                <Link href="/login">
                  <LogIn className="h-4 w-4" />
                  <span className="hidden sm:inline">Sign in</span>
                </Link>
              </Button>
            )}
            {!loading && user && (
              <Button size="sm" variant="ghost" onClick={logout} title="Sign out">
                <LogOut className="h-4 w-4" />
              </Button>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        <main className="flex-1">{children}</main>
        {!isAuthPage && <MentorSidebar />}
      </div>
      {!isAuthPage && <MentorMobileFab />}
    </div>
  );
}
