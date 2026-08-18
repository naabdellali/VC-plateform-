import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VC Investment Intelligence Platform",
  description: "Extract, research, verify, challenge, benchmark, reason, conclude.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
