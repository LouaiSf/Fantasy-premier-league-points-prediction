// 24px stroke icons for the phone navigation, drawn in currentColor.
import type { SVGProps } from "react";

function Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props} />
  );
}

export const TeamIcon = () => (
  <Icon><path d="M8 4 4 6.5 5.5 10 7 9.3V20h10V9.3l1.5.7L20 6.5 16 4a4 4 0 0 1-8 0Z" /></Icon>
);
export const TransfersIcon = () => (
  <Icon><path d="M4 8h13l-3-3" /><path d="M20 16H7l3 3" /></Icon>
);
export const CaptainIcon = () => (
  <Icon><circle cx="12" cy="12" r="8" /><path d="M14.5 9.2a3.5 3.5 0 1 0 0 5.6" /></Icon>
);
export const ChipsIcon = () => (
  <Icon><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M9 12h6M12 9v6" /></Icon>
);
export const MoreIcon = () => (
  <Icon><circle cx="5.5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="18.5" cy="12" r="1" /></Icon>
);
export const ComparisonIcon = () => (
  <Icon><path d="M12 4v16" /><path d="M4 9h5v8H4zM15 6h5v11h-5z" /></Icon>
);
export const WatchlistIcon = () => (
  <Icon><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.5" /></Icon>
);
export const FixturesIcon = () => (
  <Icon><rect x="3.5" y="5" width="17" height="15" rx="1.5" /><path d="M3.5 10h17M8 3v4M16 3v4" /></Icon>
);
export const NewsIcon = () => (
  <Icon><path d="M5 5h11v14H6a1 1 0 0 1-1-1Z" /><path d="M16 9h3v9a1 1 0 0 1-2 0M8 9h5M8 13h5" /></Icon>
);
export const StatsIcon = () => (
  <Icon><path d="M4 20h16" /><path d="M7 16v-4M12 16V7M17 16v-6" /></Icon>
);
