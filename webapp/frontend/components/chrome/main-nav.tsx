"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/components/providers/app-provider";
import { DeadlineClock } from "./deadline-clock";
import { refreshDataAndPredictions } from "@/lib/api";

const TABS = [
  { href: "/team", label: "My Team" },
  { href: "/transfers", label: "Transfer Studio" },
  { href: "/comparison", label: "Comparison" },
  { href: "/captain", label: "Captain & Form" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/chips", label: "Chip Advisor" },
  { href: "/fixtures", label: "Fixture Matrix" },
  { href: "/news", label: "News Wire" },
] as const;

export function MainNav() {
  const pathname = usePathname();
  const { snapshot, reload, toast, squadPlayers } = useApp();
  const [refreshing, setRefreshing] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const tabsRef = React.useRef<HTMLDivElement>(null);
  const inkRef = React.useRef<HTMLSpanElement>(null);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      toast(await refreshDataAndPredictions() || "Season data refreshed!");
      reload();
    } catch (err) {
      toast(`Refresh failed: ${(err as Error).message}`);
    } finally {
      setRefreshing(false);
    }
  };
  // Only alerts about the active 15. With no complete squad there is nothing
  // to attribute an alert to, so no badge is shown.
  const squadAlertCount = squadPlayers.length === 15
    ? squadPlayers.filter(
      (player) =>
        Boolean(player.news) ||
        player.status !== "a" ||
        (player.chance_of_playing_next_round ?? 100) < 100,
    ).length
    : 0;

  const positionInk = React.useCallback(() => {
    const container = tabsRef.current;
    const ink = inkRef.current;
    if (!container || !ink) return;
    const active = container.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!active) return;
    ink.style.width = `${active.offsetWidth}px`;
    ink.style.left = `${active.offsetLeft}px`;
  }, []);

  const centerActiveTab = React.useCallback(() => {
    const scroller = scrollRef.current;
    const active = tabsRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!scroller || !active || scroller.scrollWidth <= scroller.clientWidth) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    scroller.scrollTo({
      left: active.offsetLeft - (scroller.clientWidth - active.offsetWidth) / 2,
      behavior: reducedMotion ? "auto" : "smooth",
    });
  }, []);

  React.useLayoutEffect(() => {
    positionInk();
    const frame = requestAnimationFrame(() => {
      positionInk();
      centerActiveTab();
      inkRef.current?.classList.add("is-ready");
      requestAnimationFrame(() => {
        positionInk();
        centerActiveTab();
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [centerActiveTab, positionInk, pathname]);

  React.useEffect(() => {
    const container = tabsRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      positionInk();
      centerActiveTab();
    });
    observer.observe(container);
    container.querySelectorAll("a").forEach((tab) => observer.observe(tab));
    return () => observer.disconnect();
  }, [centerActiveTab, positionInk]);

  return (
    <header className="main-nav">
      <div className="shell main-nav-row">
        <Link className="brand" href="/team" aria-label="FPL Assistant home">
          <span className="brand-mark" aria-hidden="true">FPL</span>
          <span className="brand-copy">
            FPL Assistant
            <small>Prediction desk</small>
          </span>
        </Link>
        <div className="nav-scroll" ref={scrollRef}>
          <nav className="nav-tabs" role="tablist" aria-label="FPL Assistant sections" ref={tabsRef}>
            {TABS.map((tab) => {
              const active = pathname === tab.href;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  role="tab"
                  aria-selected={active}
                  className="nav-tab"
                >
                  {tab.label}
                  {tab.href === "/news" && squadAlertCount > 0 && (
                    <span
                      className="tab-count"
                      title={`${squadAlertCount} of your 15 players ${squadAlertCount === 1 ? "has" : "have"} an availability alert`}
                    >
                      <span aria-hidden="true">{squadAlertCount}</span>
                      <span className="sr-only">{squadAlertCount} squad alerts</span>
                    </span>
                  )}
                </Link>
              );
            })}
            <span className="nav-ink" ref={inkRef} aria-hidden="true" />
          </nav>
        </div>
        <div className="nav-actions">
          <button
            type="button"
            className="btn ghost sm"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Fetch the latest season data and regenerate predictions (takes a few minutes)"
            aria-label="Refresh season data"
          >
            <span className={`refresh-icon${refreshing ? " is-spinning" : ""}`} aria-hidden="true">
              ↻
            </span>
            <span className="refresh-label">{refreshing ? "Updating…" : "Refresh"}</span>
          </button>
          <DeadlineClock />
        </div>
      </div>
    </header>
  );
}
