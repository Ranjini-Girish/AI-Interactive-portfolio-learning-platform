'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { ResumeAnalysisRecord, ResumeSampleMeta, SimRole } from '@career-sim/shared';
import { SIM_ROLES } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { ResumeAnalysisView } from '@/components/resume/analysis-results';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Label } from '@/components/ui/input';
import {
  analyzeResumeSample,
  analyzeResumeText,
  fetchResumeSamples,
  uploadResumeFile,
} from '@/lib/api-client';

type Tab = 'sample' | 'paste' | 'upload';

function ResumeUploadContent() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('sample');
  const [samples, setSamples] = useState<ResumeSampleMeta[]>([]);
  const [targetRole, setTargetRole] = useState<SimRole | ''>('');
  const [pasteText, setPasteText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ResumeAnalysisRecord | null>(null);

  useEffect(() => {
    fetchResumeSamples()
      .then((r) => setSamples(r.samples))
      .catch(() => setError('Could not load sample resumes'));
  }, []);

  async function runAnalysis(fn: () => Promise<ResumeAnalysisRecord>) {
    setError('');
    setLoading(true);
    try {
      const record = await fn();
      setResult(record);
      router.replace(`/resume?id=${record.id}`, { scroll: false });
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (result) {
    return <ResumeAnalysisView record={result} />;
  }

  const roleOpt = targetRole || undefined;

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-2">Phase 3</Badge>
        <h1 className="text-2xl font-bold">Upload or analyze your resume</h1>
        <p className="mt-2 text-muted-foreground">
          We extract skills, experience, and projects — then build a learning roadmap and job match
          scores. No jargon: results are written for beginners and career returners.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Optional: target role</CardTitle>
          <CardDescription>Leave blank to auto-detect your best fit</CardDescription>
        </CardHeader>
        <CardContent>
          <select
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={targetRole}
            onChange={(e) => setTargetRole(e.target.value as SimRole | '')}
          >
            <option value="">Auto-detect best role</option>
            {SIM_ROLES.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <div className="flex gap-2 border-b border-border pb-2">
        {(['sample', 'paste', 'upload'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm capitalize ${
              tab === t ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'
            }`}
          >
            {t === 'sample' ? 'Try sample' : t}
          </button>
        ))}
      </div>

      {tab === 'sample' && (
        <div className="space-y-3">
          {samples.map((s) => (
            <Card key={s.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{s.title}</CardTitle>
                <CardDescription>{s.persona}</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-4">
                <p className="text-xs text-muted-foreground">Targets: {s.targetRoles.join(', ')}</p>
                <Button
                  size="sm"
                  disabled={loading}
                  onClick={() => runAnalysis(() => analyzeResumeSample(s.id, roleOpt))}
                >
                  Analyze
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
              <Label htmlFor="resume-text">Paste resume text</Label>
              <textarea
                id="resume-text"
                className="min-h-[240px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="Copy from Word, LinkedIn, or PDF…"
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
              />
            </div>
            <Button
              disabled={loading || pasteText.length < 80}
              onClick={() => runAnalysis(() => analyzeResumeText(pasteText, roleOpt))}
            >
              {loading ? 'Analyzing…' : 'Analyze pasted resume'}
            </Button>
          </CardContent>
        </Card>
      )}

      {tab === 'upload' && (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="space-y-2">
              <Label htmlFor="file">PDF, DOCX, or TXT (max 5 MB)</Label>
              <Input
                id="file"
                type="file"
                accept=".pdf,.docx,.txt,application/pdf,text/plain"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            <Button
              disabled={loading || !file}
              onClick={() => file && runAnalysis(() => uploadResumeFile(file, roleOpt))}
            >
              {loading ? 'Uploading…' : 'Upload & analyze'}
            </Button>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

export default function ResumePage() {
  return (
    <AuthGuard>
      <ResumeUploadContent />
    </AuthGuard>
  );
}
