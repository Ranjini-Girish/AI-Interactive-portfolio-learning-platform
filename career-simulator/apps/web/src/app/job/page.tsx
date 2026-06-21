'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { JobMatchRecord, JobSampleMeta } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { JobMatchResults } from '@/components/job/match-results';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/input';
import {
  fetchJobSamples,
  fetchLatestResume,
  matchJobSample,
  matchJobText,
} from '@/lib/api-client';

type Tab = 'sample' | 'paste';

function JobMatchContent() {
  const [tab, setTab] = useState<Tab>('sample');
  const [samples, setSamples] = useState<JobSampleMeta[]>([]);
  const [jdText, setJdText] = useState('');
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<JobMatchRecord | null>(null);

  useEffect(() => {
    fetchJobSamples()
      .then((r) => setSamples(r.samples))
      .catch(() => setError('Could not load sample job descriptions'));

    fetchLatestResume()
      .then(() => setHasResume(true))
      .catch(() => setHasResume(false));
  }, []);

  async function runMatch(fn: () => Promise<JobMatchRecord>) {
    setError('');
    setLoading(true);
    try {
      setResult(await fn());
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (result) {
    return <JobMatchResults record={result} />;
  }

  if (hasResume === false) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <h1 className="text-xl font-bold">Resume required first</h1>
        <p className="mt-2 text-muted-foreground">
          We compare the job posting against skills from your resume. Analyze a resume in Phase 3,
          then come back here.
        </p>
        <Button asChild className="mt-6">
          <Link href="/resume">Go to Resume</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-2">Phase 4</Badge>
        <h1 className="text-2xl font-bold">Match a job description</h1>
        <p className="mt-2 text-muted-foreground">
          Paste any job posting — we extract required skills, compare them to your resume, and show
          gaps, missing tools, and a learning path in plain English.
        </p>
      </header>

      <div className="flex gap-2 border-b border-border pb-2">
        {(['sample', 'paste'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm capitalize ${
              tab === t ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'
            }`}
          >
            {t === 'sample' ? 'Try sample JD' : 'Paste JD'}
          </button>
        ))}
      </div>

      {tab === 'sample' && (
        <div className="space-y-3">
          {samples.map((s) => (
            <Card key={s.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{s.title}</CardTitle>
                <CardDescription>
                  {s.company} · {s.role}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  size="sm"
                  disabled={loading || hasResume !== true}
                  onClick={() => runMatch(() => matchJobSample(s.id))}
                >
                  Match against my resume
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {tab === 'paste' && (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="space-y-2">
              <Label htmlFor="jd">Job description text</Label>
              <textarea
                id="jd"
                className="min-h-[280px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="Paste from LinkedIn, Indeed, company careers page…"
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
              />
            </div>
            <Button
              disabled={loading || jdText.length < 60 || hasResume !== true}
              onClick={() => runMatch(() => matchJobText(jdText))}
            >
              {loading ? 'Matching…' : 'Compare to my resume'}
            </Button>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

export default function JobPage() {
  return (
    <AuthGuard>
      <JobMatchContent />
    </AuthGuard>
  );
}
