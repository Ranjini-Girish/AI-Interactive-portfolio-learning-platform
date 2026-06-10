export type VoiceMode = 'browser' | 'openai';
export type TutorStatus = 'idle' | 'speaking' | 'paused';

export type AudioTutorPrefs = {
  voiceMode: VoiceMode;
  rate: number;
  autoSpeakOnStepChange: boolean;
  speakMentorReplies: boolean;
  voiceCommandsEnabled: boolean;
};

const PREFS_KEY = 'audio-tutor-prefs-v1';

export const defaultTutorPrefs: AudioTutorPrefs = {
  voiceMode: 'browser',
  rate: 1,
  autoSpeakOnStepChange: true,
  speakMentorReplies: true,
  voiceCommandsEnabled: false,
};

export function loadTutorPrefs(): AudioTutorPrefs {
  if (typeof window === 'undefined') return defaultTutorPrefs;
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return defaultTutorPrefs;
    return { ...defaultTutorPrefs, ...JSON.parse(raw) };
  } catch {
    return defaultTutorPrefs;
  }
}

export function saveTutorPrefs(prefs: AudioTutorPrefs): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

export function browserVoices(): SpeechSynthesisVoice[] {
  if (typeof window === 'undefined' || !window.speechSynthesis) return [];
  return window.speechSynthesis.getVoices();
}

export function pickVoice(): SpeechSynthesisVoice | null {
  const voices = browserVoices();
  const en =
    voices.find((v) => v.lang.startsWith('en') && /female|samantha|zira|jenny|aria/i.test(v.name)) ??
    voices.find((v) => v.lang.startsWith('en-US')) ??
    voices.find((v) => v.lang.startsWith('en')) ??
    null;
  return en;
}

let activeAudio: HTMLAudioElement | null = null;

export function speakBrowser(text: string, rate: number): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      reject(new Error('Speech synthesis not supported'));
      return;
    }
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = rate;
    const voice = pickVoice();
    if (voice) utter.voice = voice;
    utter.onend = () => resolve();
    utter.onerror = (e) => {
      // cancel() during "Next segment" fires interrupted — treat as intentional skip
      const err = (e as SpeechSynthesisErrorEvent).error;
      if (err === 'interrupted' || err === 'canceled') resolve();
      else reject(e);
    };
    window.speechSynthesis.speak(utter);
  });
}

export function pauseBrowser(): void {
  window.speechSynthesis?.pause();
}

export function resumeBrowser(): void {
  window.speechSynthesis?.resume();
}

export function stopBrowser(): void {
  window.speechSynthesis?.cancel();
}

export async function speakOpenAI(text: string): Promise<void> {
  const res = await fetch('/api/tutor/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error ?? 'OpenAI voice unavailable');
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  await new Promise<void>((resolve, reject) => {
    const audio = new Audio(url);
    activeAudio = audio;
    audio.onended = () => {
      if (activeAudio === audio) activeAudio = null;
      URL.revokeObjectURL(url);
      resolve();
    };
    audio.onerror = () => {
      if (activeAudio === audio) activeAudio = null;
      URL.revokeObjectURL(url);
      reject(new Error('Audio playback failed'));
    };
    audio.play().catch(reject);
  });
}

export async function speakLine(text: string, mode: VoiceMode, rate: number): Promise<void> {
  if (mode === 'openai') {
    try {
      await speakOpenAI(text);
      return;
    } catch {
      await speakBrowser(text, rate);
      return;
    }
  }
  await speakBrowser(text, rate);
}

export function stopAllAudio(): void {
  stopBrowser();
  if (activeAudio) {
    activeAudio.pause();
    activeAudio.currentTime = 0;
    activeAudio = null;
  }
}
