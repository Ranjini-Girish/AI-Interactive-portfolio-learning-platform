export function reverseWords(s: string): string {
  if (s === undefined || s === null) return '';
  const parts = s.trim().split(/\s+/).filter(Boolean);
  return parts.reverse().join(' ');
}

export default reverseWords;
