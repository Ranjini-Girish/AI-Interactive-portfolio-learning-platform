'use client';

import { useState } from 'react';
import type { PortfolioContent } from '@career-sim/shared';
import { SIM_ROLES } from '@career-sim/shared';
import { CopyButton } from '@/components/portfolio/copy-button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

type Tab = 'resume' | 'linkedin' | 'projects' | 'github';

const TABS: { id: Tab; label: string }[] = [
  { id: 'resume', label: 'Resume bullets' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'projects', label: 'Projects' },
  { id: 'github', label: 'GitHub README' },
];

export function PortfolioView({ content }: { content: PortfolioContent }) {
  const [tab, setTab] = useState<Tab>('resume');

  const resumeText = content.resumeBullets.map((b) => `• ${b}`).join('\n');
  const linkedInText = `${content.linkedInHeadline}\n\n${content.linkedInAbout}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">
          {content.provider === 'openai' ? 'AI-enhanced' : 'Local template'}
        </Badge>
        <span className="text-xs text-muted-foreground">
          Generated {new Date(content.generatedAt).toLocaleString()}
        </span>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{content.headline}</CardTitle>
          <CardDescription>Target: {content.targetRole}</CardDescription>
        </CardHeader>
      </Card>

      <div className="flex flex-wrap gap-2 border-b border-border pb-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              tab === t.id
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'resume' && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Resume bullet points</CardTitle>
            <CopyButton text={resumeText} />
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm leading-relaxed">
              {content.resumeBullets.map((b, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-primary">•</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {tab === 'linkedin' && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base">Headline</CardTitle>
              <CopyButton text={content.linkedInHeadline} />
            </CardHeader>
            <CardContent>
              <p className="text-sm font-medium">{content.linkedInHeadline}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-base">About section</CardTitle>
              <CopyButton text={content.linkedInAbout} />
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {content.linkedInAbout}
              </p>
            </CardContent>
          </Card>
          <CopyButton text={linkedInText} label="Copy all LinkedIn" />
        </div>
      )}

      {tab === 'projects' && (
        <div className="space-y-4">
          {content.projects.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-sm text-muted-foreground">
                Complete at least one simulation task to populate project summaries.
              </CardContent>
            </Card>
          ) : (
            content.projects.map((p, i) => (
              <Card key={i}>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base">{p.title}</CardTitle>
                    <Badge variant="outline">
                      {SIM_ROLES.find((r) => r.id === p.role)?.label ?? p.role}
                    </Badge>
                  </div>
                  <CardDescription>{p.company}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">{p.summary}</p>
                  <ul className="space-y-2 text-sm">
                    {p.bullets.map((b, j) => (
                      <li key={j}>• {b}</li>
                    ))}
                  </ul>
                  <div className="flex flex-wrap gap-1">
                    {p.skillsDemonstrated.map((s) => (
                      <Badge key={s} variant="secondary" className="text-xs">
                        {s}
                      </Badge>
                    ))}
                  </div>
                  <CopyButton
                    text={[p.title, p.summary, ...p.bullets.map((b) => `• ${b}`)].join('\n')}
                    label="Copy project"
                  />
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {tab === 'github' && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">README.md</CardTitle>
            <CopyButton text={content.githubReadme} label="Copy markdown" />
          </CardHeader>
          <CardContent>
            <pre className="max-h-[480px] overflow-auto rounded-lg bg-muted/50 p-4 text-xs leading-relaxed whitespace-pre-wrap">
              {content.githubReadme}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}