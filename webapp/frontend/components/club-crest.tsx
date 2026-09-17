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
        style={{
          display: "inline-grid",
          placeItems: "center",
          width: w,
          height: h,
          borderRadius: "50%",
          background: `linear-gradient(135deg, ${c1}, ${c2})`,
          color: "#ffffff",
          font: "700 9px/1 var(--display, sans-serif)",
          letterSpacing: "0.02em",
          flexShrink: 0,
          userSelect: "none",
          ...style,
        }}
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
