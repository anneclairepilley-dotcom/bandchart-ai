"use client";

import { useEffect, useRef, useState } from "react";
import { musicxmlDownloadUrl, type SheetStyle } from "@/lib/api";
import type { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

interface SheetMusicProps {
  projectId: string;
  instrumentKey: string;
  sheetStyle: SheetStyle;
  /** Bump to force a re-fetch (e.g. after note edits are saved). */
  notesVersion: number;
  /** Play-along transport position in seconds; null when stopped. */
  playPosition: number | null;
  /** Called with a time in seconds when the user clicks the sheet (v0.9.2). */
  onSeek?: (positionSeconds: number) => void;
  autoScroll: boolean;
}

// The exporter writes everything at a fixed 120 BPM in 4/4, so one whole
// note = 2 seconds. OSMD cursor timestamps are in whole-note units.
const SECONDS_PER_WHOLE_NOTE = 2;

/**
 * OSMD sizes its cursor overlays with width/height ATTRIBUTES on 1px-tall
 * images; Tailwind's preflight (img { height: auto }) collapses them into
 * invisible hairlines. Inline styles beat the reset, so re-apply the
 * attribute sizes after every cursor move.
 */
function fixCursorSize(cursor: { cursorElement?: HTMLImageElement }) {
  const el = cursor.cursorElement;
  if (!el) return;
  const h = el.getAttribute("height");
  const w = el.getAttribute("width");
  if (h) el.style.height = `${h}px`;
  if (w) el.style.width = `${w}px`;
  el.style.maxWidth = "none";
}

/**
 * Renders the generated MusicXML in the browser with OpenSheetMusicDisplay
 * and steps OSMD's cursor along during play-along. The cursor follows the
 * quantized beat grid of the engraved sheet, so it can differ slightly from
 * the literal recording timing — closest-note-level following, by design.
 */
export default function SheetMusic({
  projectId,
  instrumentKey,
  sheetStyle,
  notesVersion,
  playPosition,
  onSeek,
  autoScroll,
}: SheetMusicProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollBoxRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const entriesRef = useRef<
    { time: number; x: number; top: number; height: number }[]
  >([]);
  const cursorStepRef = useRef(-1);

  // Load state is keyed by the current inputs so a deps change implicitly
  // reads as "loading" without any synchronous setState in the effect.
  const depsKey = `${projectId}|${instrumentKey}|${sheetStyle}|${notesVersion}`;
  const [result, setResult] = useState<{
    key: string;
    state: "ready" | "error";
    detail?: string;
  } | null>(null);
  const loadState =
    result?.key === depsKey ? result.state : ("loading" as const);
  const errorDetail = result?.key === depsKey ? result.detail : undefined;

  useEffect(() => {
    let cancelled = false;
    const playheadEl = playheadRef.current;

    async function loadSheet() {
      try {
        const response = await fetch(
          musicxmlDownloadUrl(projectId, instrumentKey, sheetStyle)
        );
        if (!response.ok) {
          throw new Error(`MusicXML request failed (${response.status})`);
        }
        const xml = await response.text();
        if (cancelled || !containerRef.current) return;

        const { OpenSheetMusicDisplay: OSMD } = await import(
          "opensheetmusicdisplay"
        );
        if (cancelled || !containerRef.current) return;

        containerRef.current.innerHTML = "";
        const osmd = new OSMD(containerRef.current, {
          autoResize: false,
          backend: "svg",
          drawTitle: false,
          drawSubtitle: false,
          drawComposer: false,
          drawCredits: false,
          drawPartNames: true,
          // v0.9.2: bar numbers only at the start of each system, sitting
          // cleanly above the (top) staff instead of floating mid-score.
          drawMeasureNumbers: true,
          drawMeasureNumbersOnlyAtSystemStart: true,
          // Cursor 0: a soft blue wash over the current measure (visible).
          // Cursor 1: an INVISIBLE note-box cursor (alpha 0) used only to
          // measure each entry's x/y position at load time — the visible
          // note follower is our own blue playhead div, positioned by
          // interpolating between those measured positions.
          cursorsOptions: [
            { type: 3, color: "#3b82f6", alpha: 0.1, follow: false },
            { type: 0, color: "#000000", alpha: 0, follow: false },
          ],
        });
        await osmd.load(xml);
        if (cancelled) return;
        osmd.render();
        osmdRef.current = osmd;

        // Walk the invisible note cursor once to collect every entry's
        // timestamp AND on-sheet position (x, top, height), so the blue
        // playhead can be placed and interpolated deterministically.
        const entries: { time: number; x: number; top: number; height: number }[] = [];
        const walker = osmd.cursors[1];
        walker.show();
        walker.reset();
        let guard = 0;
        while (!walker.Iterator.EndReached && guard < 10000) {
          walker.update();
          fixCursorSize(walker);
          const el = walker.cursorElement;
          entries.push({
            time:
              walker.Iterator.currentTimeStamp.RealValue *
              SECONDS_PER_WHOLE_NOTE,
            x: el ? el.offsetLeft : 0,
            top: el ? el.offsetTop : 0,
            height: el
              ? el.offsetHeight ||
                parseInt(el.getAttribute("height") || "40", 10)
              : 40,
          });
          walker.next();
          guard += 1;
        }
        walker.hide();
        // Park the measure wash visibly at the start — the user should
        // always see where playback will begin on the sheet.
        const wash = osmd.cursors[0];
        wash.show();
        wash.reset();
        wash.update();
        fixCursorSize(wash);
        entriesRef.current = entries;
        cursorStepRef.current = 0;
        setResult({ key: depsKey, state: "ready" });
      } catch (err) {
        if (!cancelled) {
          setResult({
            key: depsKey,
            state: "error",
            detail: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }

    void loadSheet();
    return () => {
      cancelled = true;
      osmdRef.current = null;
      entriesRef.current = [];
      cursorStepRef.current = -1;
      // Hide the playhead while a new sheet loads (it's a sibling of the
      // OSMD container, so clearing the container doesn't remove it).
      if (playheadEl) {
        playheadEl.style.display = "none";
      }
    };
  }, [projectId, instrumentKey, sheetStyle, notesVersion, depsKey]);

  // Follow the play-along transport. The measure wash steps entry to entry;
  // the blue playhead moves CONTINUOUSLY, interpolating between the current
  // entry's position and the next one's within the same system. Pause simply
  // stops the position updates (the playhead freezes); stop (position null)
  // parks everything back at the first entry.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd || loadState !== "ready") return;
    const entries = entriesRef.current;
    if (entries.length === 0) return;

    // Target: the last entry at or before the transport position, or the
    // very first entry when stopped.
    let target = 0;
    if (playPosition !== null) {
      for (let i = 0; i < entries.length; i++) {
        if (entries[i].time <= playPosition + 1e-6) target = i;
        else break;
      }
    }

    // Step the measure wash only when the entry actually changes.
    if (target !== cursorStepRef.current) {
      const wash = osmd.cursors[0];
      if (target < cursorStepRef.current) {
        wash.reset();
        cursorStepRef.current = 0;
      }
      let guard = 0;
      while (cursorStepRef.current < target && guard < 10000) {
        wash.next();
        cursorStepRef.current += 1;
        guard += 1;
      }
      wash.update();
      fixCursorSize(wash);
    }

    // Position the blue playhead (every tick — it moves within an entry).
    const ph = playheadRef.current;
    const cur = entries[target];
    if (ph) {
      const next = entries[target + 1];
      let x = cur.x;
      if (
        playPosition !== null &&
        next &&
        next.top === cur.top &&
        next.time > cur.time
      ) {
        const f = Math.min(
          1,
          Math.max(0, (playPosition - cur.time) / (next.time - cur.time))
        );
        x = cur.x + (next.x - cur.x) * f;
      }
      ph.style.left = `${x}px`;
      ph.style.top = `${cur.top}px`;
      ph.style.height = `${Math.max(24, cur.height)}px`;
      ph.style.display = "block";
    }

    if (autoScroll && scrollBoxRef.current) {
      const box = scrollBoxRef.current;
      const phTop = cur.top;
      const viewTop = box.scrollTop;
      const viewBottom = viewTop + box.clientHeight;
      if (phTop < viewTop + 40 || phTop > viewBottom - 80) {
        box.scrollTo({
          top: Math.max(0, phTop - box.clientHeight / 3),
          behavior: "smooth",
        });
      }
    }
  }, [playPosition, autoScroll, loadState]);

  /** Click on the sheet -> seek to the nearest note entry (v0.9.2). */
  function handleSheetClick(event: React.MouseEvent<HTMLDivElement>) {
    if (!onSeek) return;
    const entries = entriesRef.current;
    if (entries.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Entry tops vary by a few pixels within one system (the note-box
    // sits at the note's height), so pick the vertically-nearest entry
    // first, then treat everything within ~100px of its top as the same
    // system band and take the horizontally closest entry in that band.
    let anchor = entries[0];
    let bestDist = Infinity;
    for (const entry of entries) {
      const dist = Math.abs(entry.top + entry.height / 2 - clickY);
      if (dist < bestDist) {
        bestDist = dist;
        anchor = entry;
      }
    }
    const band = entries.filter(
      (entry) => Math.abs(entry.top - anchor.top) < 100
    );
    let best = band[0];
    for (const entry of band) {
      if (Math.abs(entry.x - clickX) < Math.abs(best.x - clickX)) {
        best = entry;
      }
    }
    onSeek(best.time);
  }

  if (loadState === "error") {
    return (
      <p className="rounded border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900">
        Couldn&apos;t display the sheet music preview ({errorDetail}). The
        piano-roll preview above still follows playback, and the MusicXML/PDF
        downloads work independently of this viewer.
      </p>
    );
  }

  return (
    <div>
      {loadState === "loading" && (
        <p className="mb-2 text-sm text-gray-600">Rendering sheet music…</p>
      )}
      <div
        ref={scrollBoxRef}
        className="max-h-[600px] overflow-y-auto rounded border border-gray-400 bg-white p-2"
        data-testid="sheet-scrollbox"
      >
        <div
          className={`relative ${onSeek ? "cursor-pointer" : ""}`}
          onClick={handleSheetClick}
          title={onSeek ? "Click to move the playhead here" : undefined}
          data-testid="sheet-clickarea"
        >
          <div ref={containerRef} />
          <div
            ref={playheadRef}
            data-testid="sheet-playhead"
            className="pointer-events-none absolute w-[3px] rounded-full bg-blue-600/80"
            style={{ display: "none" }}
          />
        </div>
      </div>
      <p className="mt-1 text-xs text-gray-600">
        The blue line is the playhead — <span className="font-medium">click
        anywhere on the sheet to move it</span> (playback follows). It glides
        through the notes on the sheet&apos;s beat grid, with the light blue
        wash marking the current bar.
      </p>
    </div>
  );
}
