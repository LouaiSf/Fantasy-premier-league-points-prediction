"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useApp } from "@/components/providers/app-provider";
import { PlayerPhoto } from "@/components/player-photo";
import { money, num } from "@/lib/format";
import { validateSquad } from "@/lib/squad";
import type { PlayerRecord } from "@/lib/types";

const POSITIONS: PlayerRecord["position"][] = ["GK", "DEF", "MID", "FWD"];
const NEEDED: Record<string, number> = { GK: 2, DEF: 5, MID: 5, FWD: 3 };

export function SquadEditor() {
  const { snapshot, squadElements, setSquadElements, toast } = useApp();
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
  const problem = validateSquad(chosenPlayers);

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
    toast("Squad saved on this device.");
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Trigger className="btn secondary">Edit squad</DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="scrim is-open squad-scrim" />
        <DialogPrimitive.Popup
          className="picker picker-dialog"
          aria-label="Squad editor"
        >
          <div className="picker-head">
            <h3>Choose 15 players</h3>
            <label className="search">
              <span className="sr-only">Search players</span>
              <input
                type="search"
                placeholder="Search players or clubs"
                autoComplete="off"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <DialogPrimitive.Close className="btn sm secondary">Close</DialogPrimitive.Close>
          </div>
          <div className="teamsheet">
            {POSITIONS.map((position) => {
              const rows = filtered.filter((player) => player.position === position);
              if (!rows.length) return null;
              const have = chosenPlayers.filter((player) => player.position === position).length;
              return (
                <div key={position}>
                  <div className="ts-head">
                    <span className="mark">{position}</span>
                    <b>
                      {position} · {have}/{NEEDED[position]}
                    </b>
                    <span className="rule" />
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
                          {isChosen && <span className="ts-seat">Selected</span>}
                          <span className="shot">
                            {player.photo && <PlayerPhoto src={player.photo} alt="" loading="lazy" />}
                          </span>
                          <span className="ts-name">
                            <b>{player.web_name || player.name}</b>
                            <span>{player.team_short}</span>
                          </span>
                          <span className="ts-num">
                            <span className="price">{money(player.value_m)}</span>
                            <span className="proj">{num(player.predicted_points ?? player.form)}</span>
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
            <span style={{ fontSize: 12, color: problem ? "var(--pink)" : "var(--lime)" }}>
              {problem || "Legal 15-player squad ready to save."}
            </span>
            <button className="btn" type="button" disabled={Boolean(problem)} onClick={save}>
              Save squad
            </button>
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
