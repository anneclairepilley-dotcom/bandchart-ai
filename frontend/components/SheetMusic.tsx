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
  autoScroll: boolean;
}

// The exporter writes everything at a fixed 120 BPM in 4/4, so one whole
// note = 2 seconds. OSMD cursor timestamps are in whole-note units.
const SECONDS_PER_WHOLE_NOTE = 2;

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
  autoScroll,
}: SheetMusicProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollBoxRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const entryTimesRef = useRef<number[]>([]);
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
        });
        await osmd.load(xml);
        if (cancelled) return;
        osmd.render();
        osmdRef.current = osmd;

        // Walk the cursor once to collect every entry's timestamp so playback
        // can jump the cursor to the right step deterministically.
        const times: number[] = [];
        const cursor = osmd.cursor;
        cursor.show();
        cursor.reset();
        let guard = 0;
        while (!cursor.Iterator.EndReached && guard < 10000) {
          times.push(
            cursor.Iterator.currentTimeStamp.RealValue * SECONDS_PER_WHOLE_NOTE
          );
          cursor.next();
          guard += 1;
        }
        cursor.reset();
        cursor.hide();
        entryTimesRef.current = times;
        cursorStepRef.current = -1;
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
      entryTimesRef.current = [];
      cursorStepRef.current = -1;
    };
  }, [projectId, instrumentKey, sheetStyle, notesVersion, depsKey]);

  // Follow the play-along transport with OSMD's cursor.
  useEffect(() => {
    const osmd = osmdRef.current;
    if (!osmd || loadState !== "ready") return;
    const cursor = osmd.cursor;
    const times = entryTimesRef.current;

    if (playPosition === null) {
      if (cursorStepRef.current !== -1) {
        cursor.reset();
        cursor.hide();
        cursorStepRef.current = -1;
      }
      return;
    }

    // Target: the last entry at or before the transport position.
    let target = -1;
    for (let i = 0; i < times.length; i++) {
      if (times[i] <= playPosition + 1e-6) target = i;
      else break;
    }
    if (target < 0) target = 0;
    if (target === cursorStepRef.current) return;

    if (cursorStepRef.current === -1) {
      cursor.show();
    }
    if (target < cursorStepRef.current || cursorStepRef.current === -1) {
      cursor.reset();
      cursorStepRef.current = 0;
    }
    let guard = 0;
    while (cursorStepRef.current < target && guard < 10000) {
      cursor.next();
      cursorStepRef.current += 1;
      guard += 1;
    }
    cursor.update();

    if (autoScroll && cursor.cursorElement && scrollBoxRef.current) {
      const box = scrollBoxRef.current;
      const cursorTop = cursor.cursorElement.offsetTop;
      const viewTop = box.scrollTop;
      const viewBottom = viewTop + box.clientHeight;
      if (cursorTop < viewTop + 40 || cursorTop > viewBottom - 80) {
        box.scrollTo({
          top: Math.max(0, cursorTop - box.clientHeight / 3),
          behavior: "smooth",
        });
      }
    }
  }, [playPosition, autoScroll, loadState]);

  if (loadState === "error") {
    return (
      <p className="rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800">
        Couldn&apos;t display the sheet music preview ({errorDetail}). The
        piano-roll preview above still follows playback, and the MusicXML/PDF
        downloads work independently of this viewer.
      </p>
    );
  }

  return (
    <div>
      {loadState === "loading" && (
        <p className="mb-2 text-sm text-gray-500">Rendering sheet music…</p>
      )}
      <div
        ref={scrollBoxRef}
        className="max-h-[420px] overflow-y-auto rounded border border-gray-200 bg-white p-2"
        data-testid="sheet-scrollbox"
      >
        <div ref={containerRef} />
      </div>
      <p className="mt-1 text-xs text-gray-500">
        The cursor follows the sheet&apos;s beat grid, so it can sit slightly
        off the literal recording timing.
      </p>
    </div>
  );
}
