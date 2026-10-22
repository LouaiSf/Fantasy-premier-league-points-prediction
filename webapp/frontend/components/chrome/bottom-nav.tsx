"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useApp } from "@/components/providers/app-provider";
import {
  CaptainIcon, ChipsIcon, ComparisonIcon, FixturesIcon, MoreIcon, NewsIcon, StatsIcon,
  TeamIcon, TransfersIcon, WatchlistIcon,
} from "./nav-icons";

const PRIMARY = [
  { href: "/team", label: "Team", Icon: TeamIcon },
  { href: "/transfers", label: "Transfers", Icon: TransfersIcon },
  { href: "/captain", label: "Captain", Icon: CaptainIcon },
  { href: "/chips", label: "Chips", Icon: ChipsIcon },
] as const;

const MORE = [
  { href: "/comparison", label: "Comparison", Icon: ComparisonIcon },
  { href: "/watchlist", label: "Watchlist", Icon: WatchlistIcon },
  { href: "/fixtures", label: "Fixture Matrix", Icon: FixturesIcon },
  { href: "/news", label: "News Wire", Icon: NewsIcon },
  { href: "/stats", label: "Stats Lab", Icon: StatsIcon },
] as const;

/** Phone navigation (≤760px): four destinations and a More sheet for the rest. */
export function BottomNav() {
  const pathname = usePathname();
  const { squadPlayers } = useApp();
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => setOpen(false), [pathname]);

  const alerts = squadPlayers.length === 15
    ? squadPlayers.filter((p) => Boolean(p.news) || p.status !== "a" ||
        (p.chance_of_playing_next_round ?? 100) < 100).length
    : 0;
  const moreActive = MORE.some((item) => pathname?.startsWith(item.href));

  return (
    <nav className="bottom-nav" aria-label="Primary">
      {PRIMARY.map(({ href, label, Icon }) => {
        const active = pathname?.startsWith(href) ?? false;
        return (
          <Link key={href} href={href} className={`bottom-nav-item${active ? " is-active" : ""}`}
            aria-current={active ? "page" : undefined}>
            <Icon />
            <span>{label}</span>
          </Link>
        );
      })}
      <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
        <DialogPrimitive.Trigger className={`bottom-nav-item${moreActive ? " is-active" : ""}`}>
          <MoreIcon />
          <span>More</span>
          {alerts > 0 && <span className="bottom-nav-badge" aria-label={`${alerts} squad alerts`}>{alerts}</span>}
        </DialogPrimitive.Trigger>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Backdrop className="scrim bottom-sheet-scrim" />
          <DialogPrimitive.Popup className="bottom-sheet" aria-label="More pages">
            <div className="bottom-sheet-grip" aria-hidden="true" />
            <ul>
              {MORE.map(({ href, label, Icon }) => {
                const active = pathname?.startsWith(href) ?? false;
                return (
                  <li key={href}>
                    <Link href={href} className={active ? "is-active" : ""} aria-current={active ? "page" : undefined}
                      onClick={() => setOpen(false)}>
                      <Icon />
                      <span>{label}</span>
                      {href === "/news" && alerts > 0 && <span className="bottom-nav-badge">{alerts}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </DialogPrimitive.Popup>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </nav>
  );
}
