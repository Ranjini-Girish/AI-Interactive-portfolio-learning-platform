import Link from 'next/link';
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Revision Audit Viewer',
  description: 'Live visual workflow for Snorkel E2E revision flows',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-[var(--border)] bg-[var(--surface)]">
          <nav className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm">
            <Link href="/" className="font-semibold text-[var(--accent)]">
              Revision Audit
            </Link>
            <Link href="/" className="text-[var(--muted)] hover:text-[var(--text)]">
              Dashboard
            </Link>
            <Link href="/live" className="text-[var(--muted)] hover:text-[var(--text)]">
              Live tail
            </Link>
            <span className="ml-auto text-xs text-[var(--muted)]">e2e/audit → visual workflow</span>
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
