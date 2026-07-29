"use client";

import { useEffect, useRef, useState } from "react";
import { fetchTab, ApiError, type TabData } from "@/lib/api";

interface TabViewProps {
  projectId: string;
  /** A fretted instrument key: guitar, bass or ukulele. */
  instrumentKey: string;
  /** Bump to force a re-fetch (e.g. after note edits are saved). */
  notesVersion: number;
  /** Index of the note Play Along is currently sounding; null when stopped. */
  currentNoteIndex: number | null;
  /** Called with a note index when a tab column is clicked (v0.9.2 seek). */
  onSeekNote?: (noteIndex: number) => void;
  autoScroll: boolean;
}

/**
 * Text-style tablature preview for guitar/bass/ukulele. The layout comes
 * from the backend (the same code that writes the .txt download); every cell
 * is tagged with its note index so the column of the note being played can
 * be highlighted during Play Along.
 */
export default function TabView({
  projectId,
  instrumentKey,
  notesVersion,
  currentNoteIndex,
  onSeekNote,
  autoScroll,
}: TabViewProps) {
  const scrollBoxRef = useRef<HTMLDivElement>(null);

  // Load state is keyed by the current inputs so a deps change implicitly
  // reads as "loading" without any synchronous setState in the effect.
  const depsKey = `${projectId}|${instrumentKey}|${notesVersion}`;
  const [result, setResult] = useState<{
    key: string;
    state: "ready" | "error";
    data?: TabData;
    detail?: string;
  } | null>(null);
  const loadState =
    result?.key === depsKey ? result.state : ("loading" as const);
  const data = result?.key === depsKey ? result.data : undefined;
  const errorDetail = result?.key === depsKey ? result.detail : undefined;

  useEffect(() => {
    let cancelled = false;
    fetchTab(projectId, instrumentKey)
      .then((tab) => {
        if (!cancelled) setResult({ key: depsKey, state: "ready", data: tab });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setResult({
            key: depsKey,
            state: "error",
            detail:
              err instanceof ApiError || err instanceof Error
                ? err.message
                : String(err),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, instrumentKey, notesVersion, depsKey]);

  // Keep the highlighted column in view while playing, scrolling only the
  // tab box (never the page).
  useEffect(() => {
    if (!autoScroll || currentNoteIndex === null || !scrollBoxRef.current) {
      return;
    }
    const box = scrollBoxRef.current;
    const cell = box.querySelector<HTMLElement>('[data-current="true"]');
    if (!cell) return;
    const cellTop =
      cell.getBoundingClientRect().top -
      box.getBoundingClientRect().top +
      box.scrollTop;
    const viewTop = box.scrollTop;
    const viewBottom = viewTop + box.clientHeight;
    if (cellTop < viewTop + 20 || cellTop > viewBottom - 40) {
      box.scrollTo({
        top: Math.max(0, cellTop - box.clientHeight / 2),
        behavior: "smooth",
      });
    }
  }, [currentNoteIndex, autoScroll]);

  if (loadState === "error") {
    return (
      <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        Couldn&apos;t build the tab preview ({errorDetail}). The note table
        and other downloads still work — try switching instruments and back,
        or reload the page.
      </p>
    );
  }

  if (loadState === "loading" || !data) {
    return <p className="text-sm text-gray-600">Building tab…</p>;
  }

  return (
    <div>
      <p className="mb-2 text-sm text-gray-600">
        Tuning: <span className="font-medium">{data.tuning}</span>
      </p>

      {data.warnings.length > 0 && (
        <div
          className="mb-2 rounded border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800"
          data-testid="tab-warnings"
        >
          {data.warnings.map((w, i) => (
            <p key={i} className={i > 0 ? "mt-1" : undefined}>
              {w}
            </p>
          ))}
        </div>
      )}

      {data.entries.length === 0 ? (
        <p className="text-sm text-gray-600">
          No notes to show — the note list is empty.
        </p>
      ) : (
        <div
          ref={scrollBoxRef}
          className="max-h-[420px] overflow-auto rounded border border-gray-400 bg-white p-4"
          data-testid="tab-scrollbox"
        >
          <pre className="font-mono text-base leading-7" data-testid="tab-pre">
            {data.systems.map((system, sIndex) => (
              <div key={sIndex} className={sIndex > 0 ? "mt-5" : undefined}>
                {system.map((line, lIndex) => (
                  <div key={lIndex}>
                    {line.map((cell, cIndex) => {
                      const isCurrent =
                        cell.i !== null && cell.i === currentNoteIndex;
                      // Frame cells: the string name at the line start, bar
                      // lines and the trailing edge. Names dark, bars muted.
                      if (cell.i === null) {
                        return (
                          <span
                            key={cIndex}
                            className={
                              cIndex === 0
                                ? "font-semibold text-gray-900"
                                : "text-gray-600"
                            }
                          >
                            {cell.t}
                          </span>
                        );
                      }
                      // Note cells: muted dashes so the string lines read as
                      // lines, with the fret number itself bold and dark.
                      const match = /^(-*)([0-9]+|x)$/.exec(cell.t);
                      return (
                        <span
                          key={cIndex}
                          data-current={isCurrent ? "true" : undefined}
                          onClick={
                            onSeekNote && cell.i !== null
                              ? () => onSeekNote(cell.i as number)
                              : undefined
                          }
                          title={
                            onSeekNote && cell.i !== null
                              ? "Click to move the playhead here"
                              : undefined
                          }
                          className={`${
                            isCurrent ? "rounded-sm bg-orange-200 " : ""
                          }${onSeekNote && cell.i !== null ? "cursor-pointer" : ""}`}
                        >
                          {match ? (
                            <>
                              <span className="text-gray-500">{match[1]}</span>
                              <span
                                className={
                                  match[2] === "x"
                                    ? "font-bold text-red-600"
                                    : "font-bold text-gray-900"
                                }
                              >
                                {match[2]}
                              </span>
                            </>
                          ) : (
                            <span className="text-gray-600">{cell.t}</span>
                          )}
                        </span>
                      );
                    })}
                  </div>
                ))}
              </div>
            ))}
          </pre>
        </div>
      )}

      <p className="mt-1 text-xs text-gray-600">
        Each column is one detected note, in playing order (numbers are frets,
        low frets preferred). Bar lines follow the app&apos;s fixed 120 BPM
        grid. During Play Along the current column is highlighted in orange.
      </p>
    </div>
  );
}
