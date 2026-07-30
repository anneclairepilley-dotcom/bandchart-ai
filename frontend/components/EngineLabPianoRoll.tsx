"use client";

import type { LabNote } from "@/lib/engineLab";

interface Props {
  notes: LabNote[];
}

const PX_PER_SECOND = 70;
const ROW_HEIGHT = 7;
const PADDING_X = 24;
const PADDING_Y = 12;

// A small fixed palette so the same-ish group index gets a recognizably
// different color from its neighbours; ungrouped notes are plain gray.
const GROUP_COLORS = [
  "#2563eb", // blue
  "#059669", // green
  "#d97706", // amber
  "#dc2626", // red
  "#7c3aed", // violet
  "#0891b2", // cyan
];

function colorForNote(note: LabNote): string {
  if (!note.group) return "#6b7280"; // gray-500
  const match = /\d+/.exec(note.group);
  const index = match ? parseInt(match[0], 10) : 0;
  return GROUP_COLORS[index % GROUP_COLORS.length];
}

/** Minimal read-only piano-roll debug view for one Engine Lab run. */
export default function EngineLabPianoRoll({ notes }: Props) {
  if (notes.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 p-4 text-center text-xs text-gray-600">
        No notes detected.
      </div>
    );
  }

  const pitches = notes.map((n) => n.pitch);
  const minPitch = Math.min(...pitches) - 1;
  const maxPitch = Math.max(...pitches) + 1;
  const maxTime = Math.max(...notes.map((n) => n.start_time + n.duration));
  const width = PADDING_X * 2 + maxTime * PX_PER_SECOND;
  const height = PADDING_Y * 2 + (maxPitch - minPitch) * ROW_HEIGHT;

  return (
    <div className="overflow-x-auto rounded border border-gray-300 bg-white">
      <svg
        width={Math.max(200, width)}
        height={Math.max(60, height)}
        role="img"
        aria-label="Piano-roll debug view of detected notes"
        data-testid="engine-lab-piano-roll"
      >
        {notes.map((note, index) => {
          const x = PADDING_X + note.start_time * PX_PER_SECOND;
          const y = PADDING_Y + (maxPitch - note.pitch) * ROW_HEIGHT;
          const noteWidth = Math.max(2, note.duration * PX_PER_SECOND - 1);
          return (
            <rect
              key={index}
              x={x}
              y={y}
              width={noteWidth}
              height={ROW_HEIGHT - 1}
              fill={colorForNote(note)}
              opacity={0.35 + 0.65 * Math.max(0, Math.min(1, note.confidence))}
              rx={1}
            >
              <title>
                {note.pitch_name} @ {note.start_time.toFixed(2)}s
                {note.group ? ` (${note.group})` : ""}
              </title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}
