'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { SiteFooter } from '@/components/SiteFooter';

const links = [
  { href: '/start', label: 'Start here' },
  { href: '/portfolio', label: 'Try apps' },
  { href: '/build', label: 'Learn' },
  { href: '/lab/rag', label: 'RAG lab' },
  { href: '/lab/setup', label: 'Lab setup' },
  { href: '/interview', label: 'Interview' },
  { href: '/experience', label: 'Experience' },
  { href: '/contact', label: 'Contact' },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[color-mix(in_srgb,var(--bg)_92%,transparent)] backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link href="/" className="group flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--accent)] to-[#7c5cff] text-sm font-bold text-white">
              RG
            </span>
            <div className="hidden sm:block">
              <div className="text-sm font-semibold tracking-tight group-hover:text-[var(--accent)]">
                Ranjini Gowda
              </div>
              <div className="text-xs text-[var(--muted)]">Learn by trying real apps</div>
            </div>
          </Link>
          <nav className="flex items-center gap-1 text-sm sm:gap-2">
            {links.map((l) => {
              const active =
                l.href === '/'
                  ? pathname === '/'
                  : pathname === l.href || pathname.startsWith(`${l.href}/`);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  className={`rounded-lg px-2.5 py-1.5 sm:px-3 ${
                    active
                      ? 'bg-[color-mix(in_srgb,var(--accent)_18%,transparent)] text-[var(--accent)]'
                      : 'text-[var(--muted)] hover:text-[var(--text)]'
                  }`}
                >
                  {l.label}
                </Link>
              );
            })}
            <Link href="/start" className="btn-primary ml-1 hidden px-3 py-1.5 text-xs sm:inline-block">
              New? Start here
            </Link>
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
}
