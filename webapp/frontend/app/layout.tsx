import type { Metadata } from "next";
import Script from "next/script";
import "@fontsource-variable/archivo/wdth.css";
import "@fontsource-variable/inter/opsz.css";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/newsreader/opsz-italic.css";
import "@fontsource/barlow-semi-condensed/500.css";
import "@fontsource/barlow-semi-condensed/600.css";
import "@fontsource/barlow-semi-condensed/700.css";
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
