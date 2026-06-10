'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getProject } from '@/data/curriculum';
import { getDemo } from '@/data/demos';

export default function DemoLauncherPage() {
  const params = useParams();
  const slug = String(params.slug);
  const project = getProject(slug);
  const demo = getDemo(slug);
  const [online, setOnline] = useState<boolean | null>(null);
  const [embed, setEmbed] = useState(false);

  useEffect(() => {
    if (!demo?.localUrl) return;
    fetch(demo.localUrl, { mode: 'no-cors' })
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
    const t = setTimeout(() => {
      if (online === null) setOnline(false);
    }, 2500);
    return () => clearTimeout(t);
  }, [demo?.localUrl, online]);

  if (!project || !demo?.localUrl) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <h1 className="text-xl font-bold">Demo not available</h1>
        <p className="mt-2 text-[var(--muted)]">This project is not scaffolded yet.</p>
        <Link href={`/build/projects/${slug}`} className="btn-primary mt-6 inline-block">
          View learning path
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col">
      <div className="border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/portfolio" className="text-xs text-[var(--accent)] hover:underline">
              ← All apps
            </Link>
            <h1 className="text-lg font-semibold">{project.title}</h1>
            <p className="text-xs text-[var(--muted)]">{demo.startHint}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-[var(--muted)]">
              {online === null ? (
                'Checking if app is running…'
              ) : online ? (
                <span className="text-[var(--success)]">Ready — click Open below</span>
              ) : (
                <span className="text-[var(--warning)]">
                  Run START-PORTFOLIO.bat first, then refresh
                </span>
              )}
            </span>
            <a href={demo.localUrl} target="_blank" rel="noopener noreferrer" className="btn-primary text-sm">
              Open app
            </a>
            {demo.apiDocsUrl && (
              <a
                href={demo.apiDocsUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-ghost text-sm"
              >
                API
              </a>
            )}
            <button type="button" className="btn-ghost text-sm" onClick={() => setEmbed((v) => !v)}>
              {embed ? 'Hide preview' : 'Show preview here'}
            </button>
            <Link href={`/build/projects/${slug}#step-guide`} className="btn-ghost text-sm">
              Mark progress
            </Link>
          </div>
        </div>
      </div>

      {embed ? (
        <iframe
          title={project.title}
          src={demo.localUrl}
          className="min-h-[70vh] flex-1 border-0 bg-[var(--bg)]"
        />
      ) : (
        <div className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center px-4 py-16 text-center">
          <div className="card w-full text-left">
            <h2 className="font-semibold">How to open this app</h2>
            <ol className="mt-3 list-inside list-decimal space-y-2 text-sm text-[var(--muted)]">
              <li>
                Double-click <strong className="text-[var(--text)]">START-PORTFOLIO.bat</strong> on
                your computer (wait ~30 seconds).
              </li>
              <li>
                Click <strong className="text-[var(--text)]">Open app</strong> above.
              </li>
              <li>
                In the app, click <strong className="text-[var(--text)]">Start with practice data</strong>{' '}
                — no file upload needed.
              </li>
            </ol>
            <p className="mt-4 text-sm">
              Direct link:{' '}
              <a href={demo.localUrl} className="text-[var(--accent)] hover:underline">
                {demo.localUrl}
              </a>
            </p>
          </div>
          <div className="mt-6 flex flex-col items-center gap-3">
            <Link href={`/build/projects/${slug}#step-guide`} className="btn-primary text-sm">
              Finished? Mark your progress
            </Link>
            <Link href={`/build/projects/${slug}`} className="btn-ghost text-sm">
              View learning steps
            </Link>
            <Link href="/start" className="text-xs text-[var(--muted)] hover:text-[var(--accent)]">
              New here? Read the 5-minute guide
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
