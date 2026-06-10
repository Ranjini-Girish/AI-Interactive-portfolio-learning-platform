import Link from 'next/link';
import { ContactForm } from '@/components/ContactForm';
import { contact } from '@/data/resume';

export default function ContactPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8 px-4 py-10 sm:px-6">
      <header>
        <h1 className="text-3xl font-bold">Contact</h1>
        <p className="mt-2 text-[var(--muted)]">
          Interested in Gen AI engineering, ML systems, or collaboration? Send a message below.
        </p>
        <p className="mt-4 text-sm">
          <a href={`mailto:${contact.email}`} className="text-[var(--accent)] hover:underline">
            {contact.email}
          </a>
          {' · '}
          {contact.phone}
        </p>
      </header>
      <ContactForm />
    </div>
  );
}
