export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="mb-2 text-3xl font-bold text-gray-900">Privacy Policy</h1>
      <p className="mb-8 text-sm text-gray-400">Last updated: March 2026</p>

      <section className="prose prose-sm max-w-none text-gray-700 space-y-6">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Who we are</h2>
          <p>
            Jobhunter is a personal project operated by Pete Boucher
            (petebouch@gmail.com). It is an invite-only service that provides
            personalised job match scores from a shared pool of scraped job
            listings. This policy explains what personal data is collected, how
            it is used, and your rights under the General Data Protection
            Regulation (GDPR).
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">What data we collect</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>
              <strong>Account data</strong> — your name, email address, and
              Google account identifier, obtained when you sign in with Google.
            </li>
            <li>
              <strong>CV / resume</strong> — the text of any CV you voluntarily
              upload. This is used solely to extract skills and preferences for
              job matching.
            </li>
            <li>
              <strong>Job preferences</strong> — target job titles, locations,
              salary range, and remote preference that you set in the
              preferences form.
            </li>
            <li>
              <strong>Application history</strong> — jobs you save or mark as
              applied, along with any notes you add.
            </li>
            <li>
              <strong>Usage logs</strong> — server-side logs recording which API
              endpoints you call, response times, and your email address. These
              are used to diagnose errors and are not shared with third parties.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">
            Legal basis for processing
          </h2>
          <p>
            Processing is necessary to perform the service you have requested
            (GDPR Article 6(1)(b) — contract performance). Usage logs are
            processed on the basis of our legitimate interest in keeping the
            service secure and operational (Article 6(1)(f)).
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">How data is used</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>To compute personalised job match scores for you.</li>
            <li>To display your application history.</li>
            <li>To authenticate you via Google OAuth.</li>
            <li>To diagnose technical issues.</li>
          </ul>
          <p className="mt-2">
            Your data is never sold, used for advertising, or shared with third
            parties beyond the infrastructure providers listed below.
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">
            Third-party services
          </h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>
              <strong>Google OAuth</strong> — handles sign-in. Subject to
              Google&apos;s Privacy Policy.
            </li>
            <li>
              <strong>Neon (PostgreSQL)</strong> — database hosted in AWS
              eu-west-2 (Ireland). Your data is stored within the EU.
            </li>
            <li>
              <strong>Render</strong> — hosts the API server (United States).
              Only processes data transiently during request handling.
            </li>
            <li>
              <strong>Vercel</strong> — hosts the frontend (United States). No
              personal data is stored by Vercel beyond standard CDN access logs.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">Cookies</h2>
          <p>
            This service uses only strictly necessary cookies set by
            NextAuth.js: a session token (HTTPOnly JWT) and a CSRF protection
            token. These are required for the service to function and do not
            require your consent under the ePrivacy Directive. No tracking or
            analytics cookies are used.
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">
            Data retention
          </h2>
          <p>
            Your data is retained for as long as your account exists. You may
            delete your account at any time from the Profile page, which
            permanently removes all personal data associated with your account
            from our systems.
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">Your rights</h2>
          <p>Under GDPR you have the right to:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>
              <strong>Access</strong> — request a copy of the data we hold about
              you.
            </li>
            <li>
              <strong>Rectification</strong> — correct inaccurate data via the
              Profile page.
            </li>
            <li>
              <strong>Erasure</strong> — delete your account and all associated
              data via the Profile page, or by emailing petebouch@gmail.com.
            </li>
            <li>
              <strong>Portability</strong> — request an export of your data by
              emailing petebouch@gmail.com.
            </li>
            <li>
              <strong>Object</strong> — object to processing based on legitimate
              interests by emailing petebouch@gmail.com.
            </li>
          </ul>
          <p className="mt-2">
            To exercise any of these rights, contact{" "}
            <a
              href="mailto:petebouch@gmail.com"
              className="text-blue-600 underline"
            >
              petebouch@gmail.com
            </a>
            . You also have the right to lodge a complaint with your national
            data protection authority.
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold text-gray-900">Contact</h2>
          <p>
            Data controller: Pete Boucher —{" "}
            <a
              href="mailto:petebouch@gmail.com"
              className="text-blue-600 underline"
            >
              petebouch@gmail.com
            </a>
          </p>
        </div>
      </section>
    </main>
  );
}
