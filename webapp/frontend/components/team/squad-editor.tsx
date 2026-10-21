"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useApp } from "@/components/providers/app-provider";
import { Face, Pos, Proj } from "@/components/signage";
import { Icon } from "@/components/icons";
import { money } from "@/lib/format";
import { checkAffordability, fromTenths } from "@/lib/finance";
import { validateSquad } from "@/lib/squad";
import type { PlayerRecord } from "@/lib/types";

const POSITIONS: PlayerRecord["position"][] = ["GK", "DEF", "MID", "FWD"];
const NEEDED: Record<string, number> = { GK: 2, DEF: 5, MID: 5, FWD: 3 };

export function SquadEditor() {
  const { snapshot, squadElements, squadPlayers, storedSquad, setSquadElements, toast } = useApp();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  // Keyed on element rather than name: two players can share a display name,
  // and the rest of the app identifies a squad by id.
  const [selected, setSelected] = React.useState<Set<number>>(new Set());

  const players = snapshot?.players ?? [];

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      setSelected(new Set(squadElements));
      setQuery("");
    }
  }

  const filtered = players.filter((player) =>
    `${player.name} ${player.team}`.toLowerCase().includes(query.trim().toLowerCase()),
  );

  const chosenPlayers = players.filter((player) => selected.has(player.element));
  const shapeProblem = validateSquad(chosenPlayers);

  // An existing owned squad is edited against bank + the selling value of
  // whatever's dropped; a squad with no finance history yet (brand new, or
  // never priced) must simply fit the standard £100.0m budget at today's
  // prices.
  let budgetProblem = "";
  if (!shapeProblem) {
    const finance = storedSquad?.finance;
    if (finance) {
      const removed = squadPlayers.filter((player) => !selected.has(player.element));
      const added = chosenPlayers.filter((player) => !squadElements.includes(player.element));
      const affordability = checkAffordability(finance, removed, added);
      if (!affordability.affordable) {
        budgetProblem = `This edit is £${fromTenths(affordability.shortfallTenths).toFixed(1)}m over budget (bank + sale proceeds available: £${fromTenths(affordability.availableTenths).toFixed(1)}m).`;
      }
    } else {
      const totalSpend = chosenPlayers.reduce((sum, player) => sum + player.value_m, 0);
      if (totalSpend > 100.0 + 1e-9) {
        budgetProblem = `Squad costs £${totalSpend.toFixed(1)}m, £${(totalSpend - 100).toFixed(1)}m over the £100.0m budget.`;
      }
    }
  }
  const problem = shapeProblem || budgetProblem;

  function toggle(player: PlayerRecord) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(player.element)) next.delete(player.element);
      else if (next.size < 15) next.add(player.element);
      return next;
    });
  }

  function save() {
    setSquadElements([...selected]);
    setOpen(false);
    toast("Squad saved.");
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Trigger className="btn">Edit squad</DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="scrim" />
        <DialogPrimitive.Popup
          className="picker picker-dialog"
          aria-label="Squad editor"
        >
          <div className="picker-head">
            <h3>Pick your 15</h3>
            <label className="searchbox">
              <span className="sr-only">Search players</span>
              <Icon name="search" size={18} />
              <input
                className="input"
                type="search"
                placeholder="Search players or clubs"
                autoComplete="off"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <DialogPrimitive.Close className="btn btn--ghost btn--sm" aria-label="Close"><Icon name="close" size={18} /></DialogPrimitive.Close>
          </div>
          <div className="teamsheet">
            {POSITIONS.map((position) => {
              const rows = filtered.filter((player) => player.position === position);
              if (!rows.length) return null;
              const have = chosenPlayers.filter((player) => player.position === position).length;
              return (
                <div key={position}>
                  <div className="ts-head">
                    <Pos pos={position} />
                    <b>
                      {have} of {NEEDED[position]}
                    </b>
                  </div>
                  <div className="ts-rows">
                    {rows.map((player) => {
                      const isChosen = selected.has(player.element);
                      return (
                        <button
                          key={player.element}
                          type="button"
                          className={`ts-row${isChosen ? " is-chosen" : ""}`}
                          data-player-id={player.element}
                          onClick={() => toggle(player)}
                        >
                          {isChosen && <span className="ts-seat"><Icon name="check" size={14} /><span className="sr-only">Selected</span></span>}
                          <Face player={player} size="sm" />
                          <span className="ts-name">
                            <b>{player.web_name || player.name}</b>
                            <span>{player.team_short}</span>
                          </span>
                          <span className="ts-num">
                            <span className="price">{money(player.value_m)}</span>
                            <Proj value={player.predicted_points ?? player.form} />
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
            {!filtered.length && <p className="picker-empty">No players match that search.</p>}
          </div>
          <div className="dialog-actions">
            <span className={problem ? "status-line is-error" : "status-line"}>
              {problem || "That's a legal 15. Ready to save."}
            </span>
            <button className="btn btn--go" type="button" disabled={Boolean(problem)} onClick={save}>
              Save squad
            </button>
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
