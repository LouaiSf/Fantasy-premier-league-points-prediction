"use client";

import type { ImgHTMLAttributes } from "react";

interface PlayerPhotoProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "alt"> {
  alt: string;
}

// The Premier League CDN 404s for a meaningful slice of players (loans,
// youth, recent signings). Rather than let the browser show a broken-image
// icon, the layout should look the same as if no photo were ever supplied.
export function PlayerPhoto({ alt, ...props }: PlayerPhotoProps) {
  return (
    <img
      alt={alt}
      {...props}
      onError={(event) => {
        event.currentTarget.style.visibility = "hidden";
      }}
    />
  );
}
