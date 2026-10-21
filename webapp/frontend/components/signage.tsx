"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { PlayerPhoto } from "@/components/player-photo";
import { clubStyle } from "@/lib/club-colors";
import { gateFor } from "@/lib/gates";
import { num } from "@/lib/format";
import type { FixtureRecord, PlayerRecord } from "@/lib/types";

// The sign at the top of every gate: the gate number, where you are, and one
// sentence on what this place is for. Actions sit on the right of the sign.
export function GateSign({
  title,
  lede,
  children,
}: {
  readonly title?: string;
  readonly lede?: React.ReactNode;
  readonly children?: React.ReactNode;
}) {
  const pathname = usePathname();
  const gate = gateFor(pathname);
  return (
    <header className="gate-sign">
      {gate && (
        <span className="gate-sign-num" aria-hidden="true">
          {gate.n}
        </span>
      )}
      <div className="gate-sign-copy">
        <h1>{title ?? gate?.label}</h1>
        <p>{lede ?? gate?.lede}</p>
      </div>
      {children && <div className="gate-sign-actions">{children}</div>}
    </header>
  );
}

export type PlateTone = "matchday" | "stats" | "night" | "spotlight";

// The one dominant sign on a screen: the call to make, in plain words, with
// the player it is about breaking out of the top edge.
export function VerdictPlate({
  tone = "matchday",
  title,
  body,
  player,
  facts,
  actions,
  busy,
  label,
}: {
  readonly tone?: PlateTone;
  readonly title: React.ReactNode;
  readonly body?: React.ReactNode;
  readonly player?: PlayerRecord | null;
  readonly facts?: React.ReactNode;
  readonly actions?: React.ReactNode;
  readonly busy?: boolean;
  readonly label?: string;
}) {
  return (
    <section
      className={`plate plate--${tone}${player ? " has-player" : ""}${busy ? " is-busy" : ""}`}
      aria-label={label}
      aria-busy={busy || undefined}
    >
      <div className="plate-copy">
        <h2 className="plate-title">{title}</h2>
        {body && <p className="plate-body">{body}</p>}
        {facts && <div className="plate-facts">{facts}</div>}
        {actions && <div className="plate-actions">{actions}</div>}
      </div>
      {player && (
        <div className="plate-cutout" style={clubStyle(player.team)} aria-hidden="true">
          <PlayerPhoto
            key={player.element}
            src={player.photo_large ?? player.photo ?? undefined}
            fallbackSrc={player.photo ?? undefined}
            alt=""
            name={player.name}
            variant="hero"
            loading="eager"
          />
        </div>
      )}
    </section>
  );
}

export function PlateFact({ label, children }: { readonly label: string; readonly children: React.ReactNode }) {
  return (
    <span className="plate-fact">
      <small>{label}</small>
      <b>{children}</b>
    </span>
  );
}

export function Pos({ pos }: { readonly pos: PlayerRecord["position"] | string }) {
  return <span className={`pos pos--${pos}`}>{pos}</span>;
}

// Projected points on one fixed ramp, so a strong week reads before the
// figure does: a solid green block from six points, a tint from four.
export function Proj({ value, suffix }: { readonly value: number | null | undefined; readonly suffix?: string }) {
  const n = value == null ? null : Number(value);
  const band = n == null || !Number.isFinite(n) ? "none" : n >= 6 ? "hi" : n >= 4 ? "mid" : "lo";
  return (
    <span className={`proj proj--${band}`}>
      {n == null || !Number.isFinite(n) ? "–" : num(n)}
      {suffix && <small>{suffix}</small>}
    </span>
  );
}

export function Fdr({ fixture, compact }: { readonly fixture: FixtureRecord | null; readonly compact?: boolean }) {
  if (!fixture) return <span className="fdr fdr--blank">{compact ? "–" : "No game"}</span>;
  return (
    <span className={`fdr fdr--${fixture.difficulty}`} title={`Difficulty ${fixture.difficulty} of 5`}>
      {fixture.opponent}
      <small>{fixture.venue}</small>
      <span className="sr-only">, difficulty {fixture.difficulty} of 5</span>
    </span>
  );
}

// A hard limit drawn as a track: it fills toward the end stop and turns pink
// when it is full, because none of these can go past it.
export function Track({
  label,
  value,
  max,
  display,
  warnAt,
}: {
  readonly label: string;
  readonly value: number;
  readonly max: number;
  readonly display: React.ReactNode;
  readonly warnAt?: number;
}) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const full = value >= (warnAt ?? max);
  return (
    <div className={`track${full ? " is-full" : ""}`}>
      <div className="track-label">
        <span>{label}</span>
        <b>{display}</b>
      </div>
      <div
        className="track-bar"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
      >
        <i style={{ transform: `scaleX(${ratio})` }} />
      </div>
    </div>
  );
}

// A player's face on their club's colours: the cutout sits on a square tile
// so the same player reads the same in every list.
export function Face({ player, size = "md" }: { readonly player: PlayerRecord; readonly size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`face face--${size}`} style={clubStyle(player.team)}>
      <PlayerPhoto src={player.photo ?? undefined} alt="" name={player.name} variant="avatar" loading="lazy" />
    </span>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  readonly value: T;
  readonly options: readonly { readonly value: T; readonly label: React.ReactNode; readonly disabled?: boolean; readonly title?: string }[];
  readonly onChange: (value: T) => void;
  readonly label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          disabled={option.disabled}
          title={option.title}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
