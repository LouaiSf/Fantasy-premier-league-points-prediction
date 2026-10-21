import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "@fontsource-variable/archivo/wdth.css";
import "./globals.css";
import "./styles/system.css";
import "./styles/team.css";
import "./styles/screens.css";
import "./styles/drawer.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppProvider } from "@/components/providers/app-provider";
import { MotionProvider } from "@/components/motion/motion-provider";
import { MainNav } from "@/components/chrome/main-nav";
import { PlayerDrawer } from "@/components/player-drawer";
import { Toast } from "@/components/chrome/toast";

import { ErrorBoundary } from "@/components/error-boundary";

export const metadata: Metadata = {
  title: "FPL Assistant",
  description: "Your Fantasy Premier League gameweek, worked out: lineup, transfers, captain and chips.",
};

export const viewport: Viewport = {
  themeColor: "#37003c",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <head>
        {process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_DEV_OVERLAYS === "1" && (
          <>
            <Script
              src="https://unpkg.com/react-scan/dist/auto.global.js"
              crossOrigin="anonymous"
              strategy="beforeInteractive"
            />
            <Script
              src="//unpkg.com/react-grab/dist/index.global.js"
              crossOrigin="anonymous"
              strategy="beforeInteractive"
            />
          </>
        )}
      </head>
      <body>
        <TooltipProvider>
          <AppProvider>
            <MotionProvider>
              <a className="skip-link" href="#main">
                Skip to content
              </a>
              <div className="app">
                <MainNav />
                <main id="main" className="stage" tabIndex={-1}>
                  <ErrorBoundary>{children}</ErrorBoundary>
                </main>
              </div>
              <PlayerDrawer />
              <Toast />
            </MotionProvider>
          </AppProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
