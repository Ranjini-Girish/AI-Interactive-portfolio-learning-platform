'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

type SpeechCtor = new () => SpeechRecognition;

function getSpeechRecognition(): SpeechCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as Window & {
    SpeechRecognition?: SpeechCtor;
    webkitSpeechRecognition?: SpeechCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function useInterviewListener(enabled: boolean, onFinal: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [supported, setSupported] = useState(true);
  const recRef = useRef<SpeechRecognition | null>(null);
  const wantListenRef = useRef(false);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  const stop = useCallback(() => {
    wantListenRef.current = false;
    recRef.current?.stop();
    setListening(false);
  }, []);

  const start = useCallback(() => {
    const SR = getSpeechRecognition();
    if (!SR) {
      setSupported(false);
      return;
    }

    wantListenRef.current = true;

    const boot = () => {
      if (!wantListenRef.current) return;

      const rec = new SR();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onresult = (event: SpeechRecognitionEvent) => {
        let interimText = '';
        let finalText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const t = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += t;
          else interimText += t;
        }
        setInterim(interimText);
        if (finalText.trim()) onFinalRef.current(finalText.trim());
      };

      rec.onend = () => {
        setListening(false);
        if (wantListenRef.current) {
          window.setTimeout(boot, 300);
        }
      };

      rec.onerror = () => {
        setListening(false);
        if (wantListenRef.current) {
          window.setTimeout(boot, 800);
        }
      };

      recRef.current = rec;
      rec.start();
      setListening(true);
      setSupported(true);
    };

    boot();
  }, []);

  useEffect(() => {
    if (!enabled) stop();
  }, [enabled, stop]);

  useEffect(() => () => stop(), [stop]);

  return { listening, interim, supported, start, stop };
}
