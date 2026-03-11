"use client";

import { useSession, signOut } from "next-auth/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import posthog from "posthog-js";

const navLinks = [
  { href: "/feed", label: "Jobs" },
  { href: "/applications", label: "Applications" },
  { href: "/profile", label: "Profile" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      posthog.reset();
      router.push("/");
    }
    if (status === "authenticated") {
      if (!(session as any)?.isApproved) {
        router.push("/pending");
      } else if (session.user?.email) {
        posthog.identify(session.user.email, {
          name: session.user.name ?? undefined,
          email: session.user.email,
        });
      }
    }
  }, [status, session, router]);

  if (status === "loading" || !session) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar — desktop only */}
      <aside className="hidden md:flex w-56 shrink-0 border-r border-gray-200 bg-white flex-col">
        <div className="px-6 py-5 border-b border-gray-100">
          <span className="text-lg font-bold text-blue-600">Jobhunter</span>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navLinks.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex items-center rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-gray-100 px-4 py-4">
          <div className="mb-3 flex items-center gap-3">
            {session.user?.image && (
              <img
                src={session.user.image}
                alt="avatar"
                className="h-8 w-8 rounded-full"
              />
            )}
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-gray-800">
                {session.user?.name}
              </p>
              <p className="truncate text-xs text-gray-400">{session.user?.email}</p>
            </div>
          </div>
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="w-full rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200 transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col h-full overflow-hidden">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 shrink-0">
          <span className="text-lg font-bold text-blue-600">Jobhunter</span>
          {session.user?.image && (
            <img
              src={session.user.image}
              alt="avatar"
              className="h-8 w-8 rounded-full"
            />
          )}
        </header>

        <main className="flex-1 overflow-auto">{children}</main>

        {/* Bottom nav — mobile only */}
        <nav className="md:hidden shrink-0 flex border-t border-gray-200 bg-white">
          {navLinks.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex flex-1 flex-col items-center py-2 text-xs font-medium transition-colors ${
                  active ? "text-blue-600" : "text-gray-500"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="flex flex-1 flex-col items-center py-2 text-xs font-medium text-gray-500"
          >
            Sign out
          </button>
        </nav>
      </div>
    </div>
  );
}
