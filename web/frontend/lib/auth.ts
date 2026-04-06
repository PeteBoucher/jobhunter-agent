import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account }) {
      // On first sign-in, exchange Google ID token for our API JWT
      if (account?.id_token) {
        try {
          const res = await fetch(`${API_URL}/auth/google`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_token: account.id_token }),
          });
          if (res.ok) {
            const data = await res.json();
            token.apiToken = data.access_token;
            token.userId = data.user.id;
          }
        } catch {
          // API may be down; token will be missing and requests will 401
        }
      }
      return token;
    },
    async session({ session, token }) {
      (session as any).apiToken = token.apiToken;
      (session as any).userId = token.userId;
      return session;
    },
  },
});
