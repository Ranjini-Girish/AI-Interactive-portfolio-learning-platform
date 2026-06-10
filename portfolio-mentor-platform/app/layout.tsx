import type { Metadata } from 'next';
import './globals.css';
import { ConditionalShell } from '@/components/ConditionalShell';

export const metadata: Metadata = {
  title: 'Ranjini Gowda — AI Portfolio & Build Lab',
  description:
    'Hands-on AI and data learning — try real apps with step-by-step guidance. No coding required to start.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ConditionalShell>{children}</ConditionalShell>
      </body>
    </html>
  );
}
