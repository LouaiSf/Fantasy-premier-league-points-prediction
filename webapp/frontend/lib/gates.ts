// The app's destinations, numbered like stadium gates. The number is also the
// keyboard shortcut (press 1-8 anywhere outside a text field), so it carries
// information rather than decoration.
export interface Gate {
  readonly n: number;
  readonly href: string;
  readonly label: string;
  readonly lede: string;
}

export const GATES: readonly Gate[] = [
  { n: 1, href: "/team", label: "My team", lede: "Your fifteen, this week's lineup and the move worth making before the deadline." },
  { n: 2, href: "/transfers", label: "Transfers", lede: "Line up a move, check the money, and see if it's worth the hit." },
  { n: 3, href: "/captain", label: "Captain", lede: "Who should wear the armband this week, and who runs them close." },
  { n: 4, href: "/chips", label: "Chips", lede: "When to play each chip, worked out for your squad through to the end of the season." },
  { n: 5, href: "/fixtures", label: "Fixtures", lede: "Every club's next eight games, coloured by how hard they are." },
  { n: 6, href: "/comparison", label: "Compare", lede: "Put two players side by side and see who comes out ahead." },
  { n: 7, href: "/watchlist", label: "Watchlist", lede: "Good value, under-the-radar picks, and big names not pulling their weight." },
  { n: 8, href: "/news", label: "News", lede: "Injuries, suspensions and doubts, with the ones that affect you first." },
];

export function gateFor(pathname: string): Gate | undefined {
  return GATES.find((gate) => pathname === gate.href || pathname.startsWith(gate.href + "/"));
}
