import Link from 'next/link';
import { learner } from '@/data/curriculum';
import { contact } from '@/data/resume';

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-10 sm:flex-row sm:justify-between sm:px-6">
        <div>
          <p className="font-semibold">{learner.name}</p>
          <p className="mt-1 text-sm text-[var(--muted)]">{learner.title}</p>
          <p className="mt-2 text-sm">
            <a href={`mailto:${contact.email}`} className="text-[var(--accent)] hover:underline">
              {contact.email}
            </a>
            {' · '}
            {contact.phone}
          </p>
        </div>
        <nav className="flex flex-wrap gap-4 text-sm text-[var(--muted)]">
          <Link href="/portfolio" className="hover:text-[var(--text)]">
            Portfolio
          </Link>
          <Link href="/build" className="hover:text-[var(--text)]">
            Build Lab
          </Link>
          <Link href="/experience" className="hover:text-[var(--text)]">
            Experience
          </Link>
          <Link href="/plan" className="hover:text-[var(--text)]">
            Mentoring Plan
          </Link>
          <Link href="/contact" className="hover:text-[var(--text)]">
            Contact
          </Link>
        </nav>
      </div>
    </footer>
  );
}
