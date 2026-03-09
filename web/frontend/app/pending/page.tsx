"use client";

import { signOut, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function PendingPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  // If already approved, send to feed
  useEffect(() => {
    if (status === "unauthenticated") router.push("/");
    if (status === "authenticated" && (session as any)?.isApproved) {
      router.push("/feed");
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
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-10 shadow-xl text-center">
        <div className="mb-4 flex justify-center">
          <span className="text-4xl">⏳</span>
        </div>
        <h1 className="mb-2 text-2xl font-bold text-gray-900">
          You&apos;re on the waitlist
        </h1>
        {session?.user && (
          <p className="mb-4 text-sm text-gray-500">
            Signed in as{" "}
            <span className="font-medium text-gray-700">
              {session.user.email}
            </span>
          </p>
        )}
        <p className="mb-6 text-sm text-gray-500">
          Jobhunter is currently in private beta. Pete will approve your
          account and let you know when you&apos;re in.
        </p>
        <p className="mb-8 text-sm text-gray-500">
          Once approved, sign out and sign back in to access the app.
        </p>
        <button
          onClick={() => signOut({ callbackUrl: "/" })}
          className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          Sign out
        </button>
      </div>
    </main>
  );
}
