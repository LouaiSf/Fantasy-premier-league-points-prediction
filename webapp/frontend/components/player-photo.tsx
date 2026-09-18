"use client";

import * as React from "react";
import type { ImgHTMLAttributes } from "react";

interface PlayerPhotoProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "alt"> {
  alt: string;
  name?: string;
  // Tried when `src` is missing or has failed, e.g. a sharp hero image that
  // only exists for some players, backed by the small one that exists for more.
  fallbackSrc?: string;
}

// About 15% of the 2026-27 squad (mostly new signings) has no portrait on the
// Premier League CDN yet, so the fallback is a normal state rather than a rare
// edge case, and the failed request behind it is worth making exactly once.
//
// Shared across every instance rather than held per component: the same player
// appears in the market column, a shortlist and the pitch at once, and each of
// those used to fire its own request for a URL already known to be missing.
const failedUrls = new Set<string>();

export function getInitials(name?: string, fallback = ""): string {
  const target = (name || fallback || "").trim();
  if (!target) return "";
  const parts = target.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function PhotoFallback({ alt, name, className }: { alt: string; name?: string; className?: string }) {
  const initials = getInitials(name, alt);
  return (
    <span className={`photo-fb ${className || ""}`.trim()} aria-label={alt} role="img">
      <svg className="photo-fb-silhouette" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21c0-4.418 3.582-7 8-7s8 2.582 8 7" />
      </svg>
      <span className="photo-fb-initials">{initials}</span>
    </span>
  );
}

export function PlayerPhoto({
  alt,
  name,
  src,
  fallbackSrc,
  className,
  onError,
  loading = "lazy",
  decoding = "async",
  ...props
}: PlayerPhotoProps) {
  const key =
    [src, fallbackSrc].find((url): url is string => typeof url === "string" && !failedUrls.has(url)) ?? null;
  // Re-render trigger only; the Set above is the actual record.
  const [, setAttempt] = React.useState(0);

  if (!key) {
    return <PhotoFallback alt={alt} name={name} className={className} />;
  }

  return (
    <img
      alt={alt}
      src={key}
      className={className}
      loading={loading}
      decoding={decoding}
      onError={(event) => {
        failedUrls.add(key);
        setAttempt((n) => n + 1);
        onError?.(event);
      }}
      {...props}
    />
  );
}
