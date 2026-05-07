import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DEJ Intelligence",
  description:
    "The intelligence layer for nonprofit executive search. Built by a search consultant, for search consultants.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
