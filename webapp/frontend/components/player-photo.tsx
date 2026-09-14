"use client";

import * as React from "react";
import type { ImgHTMLAttributes } from "react";

interface PlayerPhotoProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "alt"> {
  alt: string;
  name?: string;
}

export function getInitials(name?: string, fallback = ""): string {
  const target = (name || fallback || "").trim();
  if (!target) return "";
  const parts = target.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function PlayerPhoto({ alt, name, src, className, onError, ...props }: PlayerPhotoProps) {
  const [hasError, setHasError] = React.useState(!src);

  React.useEffect(() => {
    setHasError(!src);
  }, [src]);

  if (hasError || !src) {
    const initials = getInitials(name, alt);
    return (
      <span className={`photo-fb ${className || ""}`.trim()} aria-label={alt} role="img">
        {initials}
      </span>
    );
  }

  return (
    <img
      alt={alt}
      src={src}
      className={className}
      onError={(event) => {
        setHasError(true);
        onError?.(event);
      }}
      {...props}
    />
  );
}

