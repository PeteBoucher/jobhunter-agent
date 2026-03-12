"use client";

import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function LandingPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") {
      router.push((session as any)?.isApproved ? "/feed" : "/pending");
    }
  }, [status, session, router]);

  if (status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-5xl mx-auto">
        <span className="text-xl font-bold text-blue-600">Jobhunter</span>
        <button
          onClick={() => signIn("google", { callbackUrl: "/" })}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          Sign in
        </button>
      </nav>

      {/* Hero */}
      <section className="flex flex-col items-center text-center px-4 pt-16 pb-12 max-w-3xl mx-auto">
        <span className="mb-4 inline-block rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
          Private beta — join the waitlist
        </span>
        <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight mb-4">
          Stop scrolling job boards.<br className="hidden sm:block" />
          See your match score instead.
        </h1>
        <p className="text-lg text-gray-600 mb-10 max-w-xl">
          Jobhunter scrapes hundreds of listings and scores every job against your CV —
          so you only see the ones worth your time.
        </p>
        <button
          onClick={() => signIn("google", { callbackUrl: "/" })}
          className="flex items-center gap-3 rounded-xl border border-gray-300 bg-white px-8 py-4 text-base font-medium text-gray-700 shadow-md hover:bg-gray-50 transition-colors"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Join the waitlist
        </button>
        <p className="mt-3 text-xs text-gray-400">Sign in with Google · we&apos;ll notify you when you&apos;re approved</p>
      </section>

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-4 py-12">
        <h2 className="text-center text-2xl font-bold text-gray-800 mb-8">How it works</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            {
              step: "1",
              title: "Upload your CV",
              body: "Drop in a PDF, Word doc, or Markdown file. Skills and experience are extracted automatically.",
            },
            {
              step: "2",
              title: "We scrape for you",
              body: "Fresh listings pulled every 6 hours from Greenhouse, Lever, LinkedIn, Workday, and more.",
            },
            {
              step: "3",
              title: "Your scored feed",
              body: "Every job scored 0–100 against your profile. Filter, save, and track applications in one place.",
            },
          ].map(({ step, title, body }) => (
            <div key={step} className="rounded-2xl bg-white p-6 shadow-sm">
              <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-600">
                {step}
              </div>
              <h3 className="mb-1 font-semibold text-gray-900">{title}</h3>
              <p className="text-sm text-gray-500">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Sources */}
      <section className="max-w-4xl mx-auto px-4 py-8 pb-16">
        <p className="text-center text-sm text-gray-400 mb-4">Sources scraped include</p>
        <p className="text-center text-sm text-gray-500 font-medium">
          Greenhouse · Lever · LinkedIn · Workday · Adzuna · Reed · The Muse · and more
        </p>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white py-6 text-center text-xs text-gray-400">
        <a href="/privacy" className="underline hover:text-gray-600">Privacy Policy</a>
        <span className="mx-3">·</span>
        <span>© {new Date().getFullYear()} Jobhunter</span>
      </footer>
    </main>
  );
}
