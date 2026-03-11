import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "next-auth/react";
import PostHogProvider from "./providers/PostHogProvider";

export const metadata: Metadata = {
  title: "Jobhunter",
  description: "AI-powered personalised job matching",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <PostHogProvider>
          <SessionProvider>{children}</SessionProvider>
        </PostHogProvider>
      </body>
    </html>
  );
}
