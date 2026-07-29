// Solo instrument choices for written parts. Mirrors the backend's
// INSTRUMENTS table in backend/app/musicxml.py — keep the two in sync.
//
// writtenOffset is the number of semitones from detected concert pitch to
// the pitch the player reads (B-flat and E-flat instruments are written
// higher than they sound). 0 means written pitch equals concert pitch.

export interface InstrumentOption {
  key: string;
  label: string;
  writtenOffset: number;
  /** Fretted instruments (guitar/bass/ukulele) show tab instead of staff notation. */
  fretted?: boolean;
  /** Standard tuning, shown with the tab output. */
  tuning?: string;
}

export const INSTRUMENTS: InstrumentOption[] = [
  { key: "concert", label: "Concert pitch", writtenOffset: 0 },
  { key: "piano", label: "Piano", writtenOffset: 0 },
  { key: "flute", label: "Flute", writtenOffset: 0 },
  { key: "violin", label: "Violin", writtenOffset: 0 },
  { key: "alto_sax", label: "Alto Sax (E♭)", writtenOffset: 9 },
  { key: "tenor_sax", label: "Tenor Sax (B♭)", writtenOffset: 14 },
  { key: "trumpet", label: "Trumpet (B♭)", writtenOffset: 2 },
  { key: "clarinet", label: "Clarinet (B♭)", writtenOffset: 2 },
  {
    key: "guitar",
    label: "Guitar",
    writtenOffset: 0,
    fretted: true,
    tuning: "E2 A2 D3 G3 B3 E4 (standard)",
  },
  {
    key: "bass",
    label: "Bass",
    writtenOffset: 0,
    fretted: true,
    tuning: "E1 A1 D2 G2 (standard)",
  },
  {
    key: "ukulele",
    label: "Ukulele",
    writtenOffset: 0,
    fretted: true,
    tuning: "G4 C4 E4 A4 (standard, high G)",
  },
];

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

/** MIDI note number -> name like "C4" (C4 = 60, matching the backend). */
export function midiNoteName(midi: number): string {
  const clamped = Math.max(0, Math.min(127, midi));
  const octave = Math.floor(clamped / 12) - 1;
  return `${NOTE_NAMES[clamped % 12]}${octave}`;
}
