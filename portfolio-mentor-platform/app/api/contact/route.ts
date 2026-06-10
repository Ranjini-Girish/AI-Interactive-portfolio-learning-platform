import { NextResponse } from 'next/server';
import { contact as owner } from '@/data/resume';

type ContactBody = {
  name: string;
  email: string;
  subject: string;
  message: string;
};

function valid(body: ContactBody): string | null {
  if (!body.name?.trim() || body.name.length > 120) return 'Invalid name';
  if (!body.email?.includes('@') || body.email.length > 200) return 'Invalid email';
  if (!body.subject?.trim() || body.subject.length > 200) return 'Invalid subject';
  if (!body.message?.trim() || body.message.length > 5000) return 'Invalid message';
  return null;
}

async function sendViaResend(body: ContactBody): Promise<boolean> {
  const key = process.env.RESEND_API_KEY;
  const to = process.env.CONTACT_TO_EMAIL ?? owner.email;
  if (!key) return false;

  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: process.env.CONTACT_FROM_EMAIL ?? 'Portfolio <onboarding@resend.dev>',
      to: [to],
      reply_to: body.email,
      subject: `[Portfolio] ${body.subject}`,
      text: `From: ${body.name} <${body.email}>\n\n${body.message}`,
    }),
  });
  return res.ok;
}

export async function POST(request: Request) {
  let body: ContactBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const err = valid(body);
  if (err) return NextResponse.json({ error: err }, { status: 422 });

  const sent = await sendViaResend(body);
  if (sent) {
    return NextResponse.json({
      message: 'Thanks — your message was sent. I will reply soon.',
      channel: 'email',
    });
  }

  const mailto = `mailto:${owner.email}?subject=${encodeURIComponent(body.subject)}&body=${encodeURIComponent(
    `From: ${body.name} (${body.email})\n\n${body.message}`,
  )}`;

  return NextResponse.json({
    message:
      'Email service not configured on this deployment. Use the mailto link below or email directly.',
    channel: 'mailto',
    mailto,
  });
}
