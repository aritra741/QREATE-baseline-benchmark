import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Particles } from "@/components/layout/Particles";
import { TooltipProvider } from "@/components/ui/tooltip";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Q-ANSWER | Query Workload-Aware Answering System for Unstructured Data",
  description: "Research demo for Q-ANSWER",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-50 text-slate-900 overflow-x-hidden`}
      >
        <TooltipProvider>
          <div className="fixed inset-0 bg-slate-100 -z-10" />
          {children}
        </TooltipProvider>
      </body>
    </html>
  );
}
