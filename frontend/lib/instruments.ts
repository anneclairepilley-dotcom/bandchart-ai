// Solo instrument choices for written parts. Mirrors the backend's
// INSTRUMENTS table in backend/app/musicxml.py — keep the two in sync.
//
// writtenOffset is the number of semitones from detected concert pitch to
// the pitch the player reads (B-flat and E-flat instruments are written
// higher than they sound). 0 means written pitch equals concert pitch.

/** Which little Web Audio patch Play Along uses for an instrument. */
export type PlaybackPatch =
  | "piano"
  | "wind"
  | "guitar"
  | "bass"
  | "uke";

export interface InstrumentOption {
  key: string;
  label: string;
  writtenOffset: number;
  /** Fretted instruments (guitar/bass/ukulele) show tab instead of staff notation. */
  fretted?: boolean;
  /** Standard tuning, shown with the tab output. */
  tuning?: string;
  /** Play Along tone when the sound selector is on Auto. */
  patch: PlaybackPatch;
}

// v0.9.8: BandChart AI is now focused around 7 real instruments. These
// stay in INSTRUMENTS (nothing is deleted — old projects saved with one of
// these still load, resolve and export fine), but the user-facing pickers
// below only ever show MAIN_INSTRUMENTS. Concert pitch can still be used
// internally for calculations, but users no longer see it as a choice.
export const INSTRUMENTS: InstrumentOption[] = [
  { key: "concert", label: "Concert pitch", writtenOffset: 0, patch: "piano" },
  { key: "piano", label: "Piano", writtenOffset: 0, patch: "piano" },
  { key: "flute", label: "Flute", writtenOffset: 0, patch: "wind" },
  { key: "violin", label: "Violin", writtenOffset: 0, patch: "wind" },
  { key: "voice", label: "Voice / Vocals", writtenOffset: 0, patch: "wind" },
  { key: "alto_sax", label: "Alto Sax (E♭)", writtenOffset: 9, patch: "wind" },
  { key: "tenor_sax", label: "Tenor Sax (B♭)", writtenOffset: 14, patch: "wind" },
  { key: "trumpet", label: "Trumpet (B♭)", writtenOffset: 2, patch: "wind" },
  { key: "clarinet", label: "Clarinet (B♭)", writtenOffset: 2, patch: "wind" },
  {
    key: "guitar",
    label: "Guitar",
    writtenOffset: 0,
    fretted: true,
    tuning: "E2 A2 D3 G3 B3 E4 (standard)",
    patch: "guitar",
  },
  {
    key: "bass",
    label: "Bass Guitar",
    writtenOffset: 0,
    fretted: true,
    tuning: "E1 A1 D2 G2 (standard)",
    patch: "bass",
  },
  {
    key: "ukulele",
    label: "Ukulele",
    writtenOffset: 0,
    fretted: true,
    tuning: "G4 C4 E4 A4 (standard, high G)",
    patch: "uke",
  },
];

// The 7 real instruments the app is now focused around. Mirrors the
// backend's instrument_profiles.py::MAIN_INSTRUMENTS — keep both in sync.
// Every other key above (concert, flute, tenor_sax, clarinet, ukulele)
// stays fully supported by the backend, just hidden from this list.
export const MAIN_INSTRUMENT_KEYS = [
  "guitar",
  "bass",
  "piano",
  "violin",
  "alto_sax",
  "trumpet",
  "voice",
];

/** The curated instrument picker list, in MAIN_INSTRUMENT_KEYS order. */
export const MAIN_INSTRUMENTS: InstrumentOption[] = MAIN_INSTRUMENT_KEYS.map(
  (key) => INSTRUMENTS.find((i) => i.key === key)!
);

/** Auto playback patch for an instrument key (piano-ish fallback). */
export function patchForInstrument(instrumentKey: string): PlaybackPatch {
  return INSTRUMENTS.find((i) => i.key === instrumentKey)?.patch ?? "piano";
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

/** MIDI note number -> name like "C4" (C4 = 60, matching the backend). */
export function midiNoteName(midi: number): string {
  const clamped = Math.max(0, Math.min(127, midi));
  const octave = Math.floor(clamped / 12) - 1;
  return `${NOTE_NAMES[clamped % 12]}${octave}`;
}
