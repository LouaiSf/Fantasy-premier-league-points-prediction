import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppProvider } from "@/components/providers/app-provider";
import { CrestTicker } from "@/components/chrome/crest-ticker";
import { MainNav } from "@/components/chrome/main-nav";
import { PlayerDrawer } from "@/components/player-drawer";
import { Toast } from "@/components/chrome/toast";

import { ErrorBoundary } from "@/components/error-boundary";

export const metadata: Metadata = {
  title: "FPL Assistant",
  description: "FPL decision support powered by this repository's local prediction pipeline.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <head>
        {process.env.NODE_ENV === "development" && (
          <Script
            src="https://unpkg.com/react-scan/dist/auto.global.js"
            crossOrigin="anonymous"
            strategy="beforeInteractive"
          />
        )}

        {process.env.NODE_ENV === "development" && (
          <Script
            src="//unpkg.com/react-grab/dist/index.global.js"
            crossOrigin="anonymous"
            strategy="beforeInteractive"
          />
        )}
        {/* eslint-disable @next/next/no-page-custom-font --
            next/font/google fetches these at build time, which was
            intermittently crashing the Turbopack build worker in this
            environment (~50% of runs). Plain <link> tags in the root
            layout head are a documented, reliable App Router alternative. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@500;600;700&family=Barlow+Semi+Condensed:wght@500;600;700&family=Inter:wght@400;450;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,700;1,6..72,500;1,6..72,600&display=swap"
          rel="stylesheet"
        />
        {/* eslint-enable @next/next/no-page-custom-font */}
      </head>
      <body>
        <TooltipProvider>
          <AppProvider>
            <a className="skip-link" href="#main">
              Skip to content
            </a>
            <CrestTicker />
            <MainNav />
            <main id="main" tabIndex={-1}>
              <ErrorBoundary>{children}</ErrorBoundary>
            </main>
            <PlayerDrawer />
            <Toast />
          </AppProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
