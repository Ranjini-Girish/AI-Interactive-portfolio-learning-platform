'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Step } from '@/data/curriculum';
import {
  loadTutorPrefs,
  saveTutorPrefs,
  speakLine,
  stopAllAudio,
  pauseBrowser,
  resumeBrowser,
  type AudioTutorPrefs,
  type TutorStatus,
  type VoiceMode,
} from '@/lib/audio-engine';
import {
  buildStepNarration,
  textForSpeech,
  type NarrationSegment,
} from '@/lib/tutor-narration';

type Props = {
  projectTitle: string;
  step: Step;
  stepNumber: number;
  totalSteps: number;
  lastMentorReply?: string;
};

export function AudioTutorPanel({
  projectTitle,
  step,
  stepNumber,
  totalSteps,
  lastMentorReply,
}: Props) {
  const [prefs, setPrefs] = useState<AudioTutorPrefs>(() => loadTutorPrefs());
  const [status, setStatus] = useState<TutorStatus>('idle');
  const [segmentIndex, setSegmentIndex] = useState(0);
  const [segments, setSegments] = useState<NarrationSegment[]>([]);
  const [error, setError] = useState('');
  const abortRef = useRef(false);
  const runIdRef = useRef(0);
  const lastSpokenMentorRef = useRef('');
  const prevStepIdRef = useRef(step.id);

  const updatePrefs = useCallback((patch: Partial<AudioTutorPrefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      saveTutorPrefs(next);
      return next;
    });
  }, []);

  const abortSpeech = useCallback(() => {
    abortRef.current = true;
    runIdRef.current += 1;
    stopAllAudio();
  }, []);

  const stop = useCallback(() => {
    abortSpeech();
    setStatus('idle');
  }, [abortSpeech]);

  const runFromIndex = useCallback(
    async (list: NarrationSegment[], start: number) => {
      const runId = ++runIdRef.current;
      abortRef.current = false;
      setSegments(list);
      setStatus('speaking');
      setError('');

      for (let i = start; i < list.length; i++) {
        if (abortRef.current || runId !== runIdRef.current) break;
        setSegmentIndex(i);
        const line = textForSpeech(list[i].text);
        try {
          await speakLine(line, prefs.voiceMode, prefs.rate);
        } catch (e) {
          if (abortRef.current || runId !== runIdRef.current) break;
          setError(e instanceof Error ? e.message : 'Speech failed');
          setStatus('idle');
          return;
        }
      }

      if (!abortRef.current && runId === runIdRef.current) setStatus('idle');
    },
    [prefs.voiceMode, prefs.rate],
  );

  const speakOneSegment = useCallback(
    async (list: NarrationSegment[], index: number) => {
      const runId = ++runIdRef.current;
      abortRef.current = false;
      setSegments(list);
      setSegmentIndex(index);
      setStatus('speaking');
      setError('');

      const seg = list[index];
      if (!seg) {
        setStatus('idle');
        return;
      }

      try {
        await speakLine(textForSpeech(seg.text), prefs.voiceMode, prefs.rate);
      } catch (e) {
        if (abortRef.current || runId !== runIdRef.current) return;
        setError(e instanceof Error ? e.message : 'Speech failed');
        setStatus('idle');
        return;
      }

      if (!abortRef.current && runId === runIdRef.current) setStatus('idle');
    },
    [prefs.voiceMode, prefs.rate],
  );

  const startWalkthrough = useCallback(() => {
    const list = buildStepNarration(projectTitle, step, stepNumber, totalSteps);
    void runFromIndex(list, 0);
  }, [projectTitle, step, stepNumber, totalSteps, runFromIndex]);

  const nextSegment = useCallback(() => {
    const list =
      segments.length > 0
        ? segments
        : buildStepNarration(projectTitle, step, stepNumber, totalSteps);

    if (segments.length === 0) {
      setSegments(list);
    }

    abortSpeech();
    const next = Math.min(segmentIndex + 1, list.length - 1);
    void speakOneSegment(list, next);
  }, [
    segments,
    segmentIndex,
    speakOneSegment,
    abortSpeech,
    projectTitle,
    step,
    stepNumber,
    totalSteps,
  ]);

  const repeatSegment = useCallback(() => {
    const list =
      segments.length > 0
        ? segments
        : buildStepNarration(projectTitle, step, stepNumber, totalSteps);

    if (segments.length === 0) {
      setSegments(list);
    }

    abortSpeech();
    void speakOneSegment(list, segmentIndex);
  }, [
    segments,
    segmentIndex,
    speakOneSegment,
    abortSpeech,
    projectTitle,
    step,
    stepNumber,
    totalSteps,
  ]);

  const readMentorReply = useCallback(async () => {
    if (!lastMentorReply) return;
    abortRef.current = false;
    setStatus('speaking');
    try {
      await speakLine(textForSpeech(lastMentorReply), prefs.voiceMode, prefs.rate);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Speech failed');
    }
    setStatus('idle');
  }, [lastMentorReply, prefs.voiceMode, prefs.rate]);

  // Auto-speak when step changes
  useEffect(() => {
    if (step.id !== prevStepIdRef.current) {
      prevStepIdRef.current = step.id;
      stop();
      setSegmentIndex(0);
      if (prefs.autoSpeakOnStepChange) {
        const t = setTimeout(() => startWalkthrough(), 600);
        return () => clearTimeout(t);
      }
    }
  }, [step.id, prefs.autoSpeakOnStepChange, startWalkthrough, stop]);

  // Speak new mentor replies
  useEffect(() => {
    if (
      !prefs.speakMentorReplies ||
      !lastMentorReply ||
      lastMentorReply === lastSpokenMentorRef.current
    ) {
      return;
    }
    lastSpokenMentorRef.current = lastMentorReply;
    void readMentorReply();
  }, [lastMentorReply, prefs.speakMentorReplies, readMentorReply]);

  // Voice commands
  useEffect(() => {
    if (!prefs.voiceCommandsEnabled) return;

    const SR =
      typeof window !== 'undefined'
        ? window.SpeechRecognition ?? window.webkitSpeechRecognition
        : undefined;

    if (!SR) return;

    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = 'en-US';

    rec.onresult = (event: SpeechRecognitionEvent) => {
      const last = event.results[event.results.length - 1];
      if (!last?.isFinal) return;
      const said = last[0].transcript.toLowerCase().trim();

      if (/start|begin|tutorial|walkthrough|read step/.test(said)) startWalkthrough();
      else if (/next|skip|continue/.test(said)) nextSegment();
      else if (/repeat|again|replay/.test(said)) repeatSegment();
      else if (/stop|quiet|pause tutor/.test(said)) stop();
      else if (/mentor|feedback/.test(said)) void readMentorReply();
    };

    rec.onerror = () => {};
    rec.start();

    return () => {
      try {
        rec.stop();
      } catch {
        /* ignore */
      }
    };
  }, [
    prefs.voiceCommandsEnabled,
    startWalkthrough,
    nextSegment,
    repeatSegment,
    stop,
    readMentorReply,
  ]);

  const current = segments[segmentIndex];
  const segmentLabel =
    segments.length > 0
      ? `Segment ${segmentIndex + 1} of ${segments.length}`
      : null;

  return (
    <div className="card border-[var(--accent)]/40 bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-lg" aria-hidden>
              🎧
            </span>
            <h2 className="text-lg font-semibold">Audio AI Tutor</h2>
            {status === 'speaking' && (
              <span className="badge domain-genai animate-pulse">Speaking</span>
            )}
          </div>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Hands-free step-by-step guidance while you code. Works in Chrome/Edge with browser
            voice; add OpenAI key for premium voice.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-primary text-sm" onClick={startWalkthrough}>
            Start walkthrough
          </button>
          {status === 'speaking' ? (
            <>
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={() => {
                  if (status === 'speaking') {
                    pauseBrowser();
                    setStatus('paused');
                  }
                }}
              >
                Pause
              </button>
              <button type="button" className="btn-ghost text-sm" onClick={stop}>
                Stop
              </button>
            </>
          ) : status === 'paused' ? (
            <>
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={() => {
                  resumeBrowser();
                  setStatus('speaking');
                }}
              >
                Resume
              </button>
              <button type="button" className="btn-ghost text-sm" onClick={stop}>
                Stop
              </button>
            </>
          ) : null}
        </div>
      </div>

      {segmentLabel && (
        <p className="mt-2 text-xs text-[var(--muted)]">{segmentLabel}</p>
      )}

      {current && (
        <p className="mt-3 rounded-lg bg-[var(--bg)] px-3 py-2 text-sm">
          <span className="text-[var(--accent)]">{current.label}: </span>
          {current.text.slice(0, 200)}
          {current.text.length > 200 ? '…' : ''}
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-xs">
          <span className="text-[var(--muted)]">Voice</span>
          <select
            className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-sm"
            value={prefs.voiceMode}
            onChange={(e) => updatePrefs({ voiceMode: e.target.value as VoiceMode })}
          >
            <option value="browser">Browser (free)</option>
            <option value="openai">OpenAI premium</option>
          </select>
        </label>
        <label className="text-xs">
          <span className="text-[var(--muted)]">Speed {prefs.rate.toFixed(1)}×</span>
          <input
            type="range"
            min={0.7}
            max={1.3}
            step={0.1}
            value={prefs.rate}
            onChange={(e) => updatePrefs({ rate: Number(e.target.value) })}
            className="mt-1 w-full"
          />
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={prefs.autoSpeakOnStepChange}
            onChange={(e) => updatePrefs({ autoSpeakOnStepChange: e.target.checked })}
          />
          Auto-speak new steps
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={prefs.speakMentorReplies}
            onChange={(e) => updatePrefs({ speakMentorReplies: e.target.checked })}
          />
          Read mentor replies aloud
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--border)] pt-3">
        <button type="button" className="btn-ghost text-xs" onClick={nextSegment}>
          Next segment
        </button>
        <button type="button" className="btn-ghost text-xs" onClick={repeatSegment}>
          Repeat
        </button>
        {lastMentorReply && (
          <button type="button" className="btn-ghost text-xs" onClick={() => void readMentorReply()}>
            Read mentor reply
          </button>
        )}
        <label className="ml-auto flex items-center gap-2 text-xs text-[var(--muted)]">
          <input
            type="checkbox"
            checked={prefs.voiceCommandsEnabled}
            onChange={(e) => updatePrefs({ voiceCommandsEnabled: e.target.checked })}
          />
          Voice commands (say &quot;next&quot;, &quot;repeat&quot;, &quot;stop&quot;)
        </label>
      </div>

      {error && <p className="mt-2 text-xs text-[var(--danger)]">{error}</p>}
    </div>
  );
}
