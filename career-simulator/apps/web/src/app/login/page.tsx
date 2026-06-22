'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, useState, Suspense } from 'react';
import { SignIn } from '@clerk/nextjs';
import { getAuthErrorMessage, useAuth } from '@/components/providers/auth-provider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Label } from '@/components/ui/input';
import { isClerkEnabled } from '@/lib/clerk-config';

function LegacyLoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get('next') ?? '/dashboard';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      router.push(next);
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle>Welcome back</CardTitle>
        <CardDescription>
          Sign in to save your progress and start your work simulation.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          New here?{' '}
          <Link href="/register" className="text-primary hover:underline">
            Create a free account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

function ClerkLogin() {
  const searchParams = useSearchParams();
  const next = searchParams.get('next') ?? '/dashboard';

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-4">
      <SignIn signUpUrl="/register" forceRedirectUrl={next} fallbackRedirectUrl={next} />
    </div>
  );
}

function LoginContent() {
  if (isClerkEnabled()) {
    return <ClerkLogin />;
  }
  return <LegacyLoginForm />;
}

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <Suspense fallback={<p className="text-center text-muted-foreground">Loading…</p>}>
        <LoginContent />
      </Suspense>
    </div>
  );
}
