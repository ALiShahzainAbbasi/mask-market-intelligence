import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MASK AI | Local System Status",
  description:
    "Local development infrastructure for the MASK AI Market Intelligence & Selection System.",
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
