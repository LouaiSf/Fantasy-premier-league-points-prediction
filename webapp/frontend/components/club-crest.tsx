"use client";

import * as React from "react";
import type { ImgHTMLAttributes } from "react";
import { crestUrl } from "@/lib/format";
import { getClubColors } from "@/lib/club-colors";

interface ClubCrestProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt"> {
  code?: number | null;
  team?: string;
  shortName?: string;
  size?: number;
  alt?: string;
}

export function ClubCrest({
  code,
  team,
  shortName,
  size = 100,
  alt = "",
  className,
  width,
  height,
  style,
  onError,
  loading = "lazy",
  decoding = "async",
  ...props
}: ClubCrestProps) {
  const [failedCode, setFailedCode] = React.useState<number | null>(null);
  const hasError = !code || failedCode === code;

  if (hasError || !code) {
    const [c1, c2] = getClubColors(team || "");
    const abbrev = (shortName || (team ? team.slice(0, 3) : "FPL")).toUpperCase();
    const w = width ?? (typeof size === "number" && size <= 32 ? size : 24);
    const h = height ?? (typeof size === "number" && size <= 32 ? size : 24);

    return (
      <span
        className={`crest-fallback ${className || ""}`.trim()}
        style={{ width: w, height: h, background: `linear-gradient(135deg, ${c1}, ${c2})`, ...style }}
        aria-label={alt || team || "Club crest"}
        role="img"
      >
        {abbrev}
      </span>
    );
  }

  return (
    <img
      src={crestUrl(code, size)}
      alt={alt}
      className={className}
      width={width}
      height={height}
      style={style}
      loading={loading}
      decoding={decoding}
      onError={(event) => {
        setFailedCode(code);
        onError?.(event);
      }}
      {...props}
    />
  );
}
