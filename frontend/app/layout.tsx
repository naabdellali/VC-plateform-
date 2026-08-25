import type { Metadata } from "next";
import "./globals.css";

// Fonts for the dashboard + new-dossier screens only (see the .dash-* / .new-dossier-*
// rules in globals.css) - the rest of the app (tray, memo, module drill-downs) keeps
// its existing system font stack untouched, since only these two screens' redesign
// was approved.
//
// Loaded via a plain <link> (fetched by the browser at runtime) rather than
// next/font/google, which fetches the font files at BUILD TIME - that fetch is
// blocked in network-restricted build environments. A <link> tag has no such
// requirement and degrades gracefully to the "Public Sans"/"IBM Plex Mono"
// fallback names (see globals.css) if it's ever slow to load.
export const metadata: Metadata = {
  title: "VC Investment Intelligence Platform",
  description: "Extract, research, verify, challenge, benchmark, reason, conclude.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
