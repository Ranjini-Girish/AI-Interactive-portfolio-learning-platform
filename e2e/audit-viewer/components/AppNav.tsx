'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { IconLayoutGrid, IconRadio, IconTerminal } from './icons';

const NAV = [
  { href: '/', label: 'Dashboard', icon: IconLayoutGrid },
  { href: '/live', label: 'Live tail', icon: IconRadio },
] as const;

export function AppNav() {
  const pathname = usePathname();

  return (
    <header className="app-header">
      <nav className="app-nav" aria-label="Main">
        <Link href="/" className="brand-link">
          <IconTerminal className="h-5 w-5 text-[var(--accent)]" />
          <span>Revision Audit</span>
        </Link>
        <div className="nav-links">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`nav-link ${active ? 'nav-link-active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </div>
        <p className="nav-meta">e2e/audit · 5s refresh</p>
      </nav>
    </header>
  );
}
