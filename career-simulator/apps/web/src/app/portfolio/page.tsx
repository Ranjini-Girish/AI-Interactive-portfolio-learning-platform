'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Loader2, Sparkles } from 'lucide-react';
import type { PortfolioRecord } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { PortfolioView } from '@/components/portfolio/portfolio-view';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  fetchLatestPortfolio,
  fetchPortfolioStatus,
  generatePortfolioContent,
} from '@/lib/api-client';

function PortfolioContent() {
  const [record, setRecord] = useState<PortfolioRecord | null>(null);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [aiConfigured, setAiConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchPortfolioStatus()
      .then((s) => {
        setHasResume(s.hasResume);
        setAiConfigured(s.configured);
        if (s.hasGeneration) {
          return fetchLatestPortfolio().then(setRecord);
        }
      })
      .catch(() => setError('Could not load portfolio status'))
      .finally(() => setLoading(false));
  }, []);

  async function handleGenerate() {
    setError('');
    setGenerating(true);
    try {
      setRecord(await generatePortfolioContent());
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return <p className="p-10 text-center text-muted-foreground">Loading…</p>;
  }

  if (hasResume === false) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <h1 className="text-xl font-bold">Resume required</h1>
        <p className="mt-2 text-muted-foreground">
          We build your portfolio from resume analysis, job match, and simulation work.
        </p>
        <Button asChild className="mt-6">
          <Link href="/resume">Analyze resume first</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-2">Phase 8 — Portfolio generator</Badge>
        <h1 className="text-2xl font-bold">Your portfolio</h1>
        <p className="mt-2 text-muted-foreground">
          Auto-generated resume bullets, LinkedIn copy, project summaries, and GitHub README —
          built from your real practice work.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Generate artifacts</CardTitle>
          <CardDescription>
            {aiConfigured
              ? 'Uses OpenAI for polished copy (falls back to templates if unavailable).'
              : 'Local template mode — add OPENAI_API_KEY for AI-enhanced output.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button onClick={handleGenerate} disabled={generating}>
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Generating…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                {record ? 'Regenerate portfolio' : 'Generate portfolio'}
              </>
            )}
          </Button>
          <Button asChild variant="outline">
            <Link href="/roles">Add simulation work</Link>
          </Button>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {record ? (
        <PortfolioView content={record.content} />
      ) : (
        <Card className="border-dashed">
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Click Generate to create your first portfolio package.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function PortfolioPage() {
  return (
    <AuthGuard>
      <PortfolioContent />
    </AuthGuard>
  );
}
