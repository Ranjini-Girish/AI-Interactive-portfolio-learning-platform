import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { ThemeProvider } from '@/components/providers/theme-provider';
import { AuthProvider } from '@/components/providers/auth-provider';
import { MentorProvider } from '@/components/providers/mentor-provider';
import { AppShell } from '@/components/layout/app-shell';
import './globals.css';

const geist = Geist({ subsets: ['latin'], variable: '--font-geist' });
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' });

export const metadata: Metadata = {
  title: 'AI Career Transition Simulator',
  description:
    'Practice real company work — guided by an AI mentor. For beginners, returners, and upskillers.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geist.variable} ${geistMono.variable} font-sans`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <AuthProvider>
            <MentorProvider>
              <AppShell>{children}</AppShell>
            </MentorProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
