import type { SVGProps } from "react";

// One drawn set: 24px grid, 2px square-capped strokes, so arrows read like
// the wayfinding arrows they stand for rather than like emoji.
const PATHS = {
  "arrow-right": "M4 12h15M13 6l6 6-6 6",
  "arrow-left": "M20 12H5M11 6l-6 6 6 6",
  "arrow-up": "M12 20V5M6 11l6-6 6 6",
  "arrow-down": "M12 4v15M6 13l6 6 6-6",
  "chevron-right": "M9 5l7 7-7 7",
  "chevron-down": "M5 9l7 7 7-7",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  close: "M6 6l12 12M18 6L6 18",
  search: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.5 15.5L20 20",
  swap: "M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4",
  menu: "M4 7h16M4 12h16M4 17h16",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  check: "M5 12.5l4.5 4.5L19 7.5",
  alert: "M12 4l9 16H3zM12 10v4M12 17v.5",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  download: "M12 4v11M7 10l5 5 5-5M5 20h14",
  upload: "M12 20V9M7 14l5-5 5 5M5 4h14",
  more: "M5 12h.01M12 12h.01M19 12h.01",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, ...props }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3.2 : 2}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
