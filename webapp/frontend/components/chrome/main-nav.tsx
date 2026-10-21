"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useApp } from "@/components/providers/app-provider";
import { DeadlineClock } from "./deadline-clock";
import { Icon } from "@/components/icons";
import { refreshDataAndPredictions } from "@/lib/api";
import { GATES, gateFor } from "@/lib/gates";
import { isFlagged } from "@/lib/why";

// Phone gate bar: the four gates used closest to a deadline, then a sheet
// with the rest. Eight tabs in a scroller hid the fourth one off-screen.
const PHONE_GATES = ["/team", "/transfers", "/captain", "/chips"];

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 40 40" width="40" height="40">
        <rect width="40" height="40" fill="var(--green)" />
        <path d="M9 10h14v5H15v4h7v5h-7v7H9z" fill="var(--pl-purple)" />
        <path d="M25 13l7 7-7 7" fill="none" stroke="var(--pl-purple)" strokeWidth="4" strokeLinecap="square" />
      </svg>
    </span>
  );
}

function useAlertCount() {
  const { squadPlayers } = useApp();
  return squadPlayers.length === 15 ? squadPlayers.filter(isFlagged).length : 0;
}

function RefreshButton({ compact }: { readonly compact?: boolean }) {
  const { reload, toast } = useApp();
  const [refreshing, setRefreshing] = React.useState(false);
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      toast((await refreshDataAndPredictions()) || "Latest prices, news and projections are in.");
      reload();
    } catch (err) {
      toast(`Couldn't refresh: ${(err as Error).message}`);
    } finally {
      setRefreshing(false);
    }
  };
  return (
    <button
      type="button"
      className={`rail-refresh${refreshing ? " is-busy" : ""}`}
      onClick={handleRefresh}
      disabled={refreshing}
      title="Pull the latest prices and news, then update the projections. Takes a few minutes."
    >
      <Icon name="refresh" size={16} />
      {!compact && <span>{refreshing ? "Updating…" : "Get latest data"}</span>}
      {compact && <span className="sr-only">Get latest data</span>}
    </button>
  );
}

export function MainNav() {
  const pathname = usePathname();
  const router = useRouter();
  const alerts = useAlertCount();
  const [moreOpen, setMoreOpen] = React.useState(false);
  const listRef = React.useRef<HTMLOListElement>(null);
  const plateRef = React.useRef<HTMLSpanElement>(null);
  const active = gateFor(pathname);

  // The white active-gate plate travels between gates instead of jumping.
  const placePlate = React.useCallback(() => {
    const list = listRef.current;
    const plate = plateRef.current;
    if (!list || !plate) return;
    const current = list.querySelector<HTMLElement>('[aria-current="page"]');
    if (!current) {
      plate.style.opacity = "0";
      return;
    }
    plate.style.opacity = "1";
    plate.style.transform = `translateY(${current.offsetTop}px)`;
    plate.style.height = `${current.offsetHeight}px`;
  }, []);

  React.useLayoutEffect(() => {
    placePlate();
    const frame = requestAnimationFrame(() => plateRef.current?.classList.add("is-ready"));
    return () => cancelAnimationFrame(frame);
  }, [pathname, placePlate]);

  React.useEffect(() => {
    window.addEventListener("resize", placePlate);
    return () => window.removeEventListener("resize", placePlate);
  }, [placePlate]);

  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
      if (document.querySelector('[role="dialog"]')) return;
      const gate = GATES.find((item) => String(item.n) === event.key);
      if (gate) {
        event.preventDefault();
        router.push(gate.href);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const alertBadge = (href: string) =>
    href === "/news" && alerts > 0 ? (
      <span className="gate-alert" title={`${alerts} of your 15 have an availability flag`}>
        <span aria-hidden="true">{alerts}</span>
        <span className="sr-only">{alerts} squad alerts</span>
      </span>
    ) : null;

  return (
    <>
      <aside className="rail" aria-label="Main">
        <Link className="brand" href="/team" aria-label="FPL Assistant, my team">
          <BrandMark />
          <span className="brand-name">
            FPL<br />Assistant
          </span>
        </Link>
        <nav className="gates" aria-label="Sections">
          <span className="gate-plate" ref={plateRef} aria-hidden="true" />
          <ol ref={listRef}>
            {GATES.map((gate) => {
              const current = active?.href === gate.href;
              return (
                <li key={gate.href}>
                  <Link
                    href={gate.href}
                    className="gate"
                    aria-current={current ? "page" : undefined}
                    aria-keyshortcuts={String(gate.n)}
                  >
                    <span className="gate-num" aria-hidden="true">{gate.n}</span>
                    <span className="gate-label">{gate.label}</span>
                    {alertBadge(gate.href)}
                    <Icon className="gate-arrow" name="arrow-right" size={18} />
                  </Link>
                </li>
              );
            })}
          </ol>
        </nav>
        <div className="rail-foot">
          <DeadlineClock />
          <RefreshButton />
          <p className="rail-hint">Press 1–8 to jump between sections</p>
        </div>
      </aside>

      <header className="topbar">
        <Link className="brand" href="/team" aria-label="FPL Assistant, my team">
          <BrandMark />
          <span className="brand-name">FPL Assistant</span>
        </Link>
        <DeadlineClock variant="compact" />
        <RefreshButton compact />
      </header>

      <nav className="gatebar" aria-label="Sections">
        {GATES.filter((gate) => PHONE_GATES.includes(gate.href)).map((gate) => (
          <Link
            key={gate.href}
            href={gate.href}
            className="gatebar-item"
            aria-current={active?.href === gate.href ? "page" : undefined}
            onClick={() => setMoreOpen(false)}
          >
            <span className="gate-num" aria-hidden="true">{gate.n}</span>
            <span>{gate.label}</span>
          </Link>
        ))}
        <button
          type="button"
          className="gatebar-item"
          aria-expanded={moreOpen}
          aria-controls="more-gates"
          aria-current={active && !PHONE_GATES.includes(active.href) ? "page" : undefined}
          onClick={() => setMoreOpen((open) => !open)}
        >
          <span className="gate-num" aria-hidden="true">
            <Icon name={moreOpen ? "close" : "more"} size={18} />
          </span>
          <span>{active && !PHONE_GATES.includes(active.href) ? active.label : "More"}</span>
          {alerts > 0 && <span className="gate-alert gate-alert--dot" aria-hidden="true" />}
        </button>
      </nav>
      <div id="more-gates" className={`more-sheet${moreOpen ? " is-open" : ""}`} hidden={!moreOpen}>
        <div className="more-scrim" onClick={() => setMoreOpen(false)} aria-hidden="true" />
        <ul>
          {GATES.filter((gate) => !PHONE_GATES.includes(gate.href)).map((gate) => (
            <li key={gate.href}>
              <Link
                href={gate.href}
                className="gate"
                aria-current={active?.href === gate.href ? "page" : undefined}
                onClick={() => setMoreOpen(false)}
              >
                <span className="gate-num" aria-hidden="true">{gate.n}</span>
                <span className="gate-label">
                  {gate.label}
                  <small>{gate.lede}</small>
                </span>
                {alertBadge(gate.href)}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
