import type { Note } from "@/lib/api";

interface NotePreviewProps {
  notes: Note[];
}

const PX_PER_SECOND = 60;
const ROW_HEIGHT = 8;
const PADDING_X = 40;
const PADDING_Y = 16;

/**
 * Plain-SVG piano-roll style preview of a transcription.
 * x axis = time in seconds, y axis = MIDI pitch (higher pitch drawn higher
 * on screen). One <rect> per note; opacity scales with confidence.
 */
export default function NotePreview({ notes }: NotePreviewProps) {
  if (notes.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
        No notes were detected.
      </div>
    );
  }

  const pitches = notes.map((n) => n.pitch);
  const minPitch = Math.min(...pitches) - 2;
  const maxPitch = Math.max(...pitches) + 2;
  const maxTime = Math.max(...notes.map((n) => n.start_time + n.duration));

  const width = Math.max(400, maxTime * PX_PER_SECOND + PADDING_X * 2);
  const height = (maxPitch - minPitch + 1) * ROW_HEIGHT + PADDING_Y * 2;

  const pitchToY = (pitch: number) =>
    PADDING_Y + (maxPitch - pitch) * ROW_HEIGHT;

  // Horizontal gridlines + labels at each C (octave boundaries).
  const octaveLines: { pitch: number; label: string }[] = [];
  for (let p = Math.ceil(minPitch / 12) * 12; p <= maxPitch; p += 12) {
    octaveLines.push({ pitch: p, label: pitchNameFromMidi(p) });
  }

  // Vertical gridlines every N seconds, chosen so there aren't too many.
  const secondsStep = maxTime > 60 ? 10 : maxTime > 20 ? 5 : 1;
  const timeLines: number[] = [];
  for (let t = 0; t <= maxTime; t += secondsStep) {
    timeLines.push(t);
  }

  return (
    <div className="w-full overflow-x-auto rounded border border-gray-200 bg-white">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Piano roll preview of transcribed notes"
        className="block"
      >
        {/* Octave gridlines + pitch labels */}
        {octaveLines.map(({ pitch, label }) => (
          <g key={pitch}>
            <line
              x1={PADDING_X}
              x2={width - PADDING_X + 8}
              y1={pitchToY(pitch)}
              y2={pitchToY(pitch)}
              stroke="#e5e7eb"
              strokeWidth={1}
            />
            <text
              x={4}
              y={pitchToY(pitch) + 3}
              fontSize={9}
              fill="#6b7280"
            >
              {label}
            </text>
          </g>
        ))}

        {/* Time gridlines + labels */}
        {timeLines.map((t) => (
          <g key={t}>
            <line
              x1={PADDING_X + t * PX_PER_SECOND}
              x2={PADDING_X + t * PX_PER_SECOND}
              y1={PADDING_Y}
              y2={height - PADDING_Y + 8}
              stroke="#f3f4f6"
              strokeWidth={1}
            />
            <text
              x={PADDING_X + t * PX_PER_SECOND}
              y={height - 4}
              fontSize={9}
              fill="#6b7280"
              textAnchor="middle"
            >
              {t}s
            </text>
          </g>
        ))}

        {/* Notes */}
        {notes.map((note, i) => {
          const confidence = Math.min(1, Math.max(0, note.confidence));
          const x = PADDING_X + note.start_time * PX_PER_SECOND;
          const w = Math.max(2, note.duration * PX_PER_SECOND);
          const y = pitchToY(note.pitch);
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={w}
              height={ROW_HEIGHT - 1}
              rx={1}
              fill="#2563eb"
              fillOpacity={0.15 + confidence * 0.75}
            >
              <title>
                {note.pitch_name} @ {note.start_time.toFixed(2)}s for{" "}
                {note.duration.toFixed(2)}s (confidence{" "}
                {(confidence * 100).toFixed(0)}%)
              </title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

const NOTE_NAMES = [
  "C",
  "C#",
  "D",
  "D#",
  "E",
  "F",
  "F#",
  "G",
  "G#",
  "A",
  "A#",
  "B",
];

function pitchNameFromMidi(pitch: number): string {
  const name = NOTE_NAMES[((pitch % 12) + 12) % 12];
  const octave = Math.floor(pitch / 12) - 1;
  return `${name}${octave}`;
}
