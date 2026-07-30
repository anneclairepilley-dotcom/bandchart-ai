"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Note } from "@/lib/api";
import { patchForInstrument, type PlaybackPatch } from "@/lib/instruments";

interface PlayAlongProps {
  notes: Note[];
  /** Selected instrument key — picks the playback tone when Sound is Auto. */
  instrumentKey: string;
  /**
   * Called every animation frame while playing (and once on pause/stop) with
   * the transport position in seconds and the index of the sounding note.
   * Both are null when playback is stopped.
   */
  onTick: (position: number | null, noteIndex: number | null) => void;
  /**
   * Hands the parent a seek(seconds) function (v0.9.2 click-to-seek):
   * playing → jump and keep playing; paused → move the frozen position;
   * stopped → set where the next Play will start (playhead moves too).
   */
  registerSeek?: (seek: (positionSeconds: number) => void) => void;
  autoScroll: boolean;
  onAutoScrollChange: (value: boolean) => void;
}

type Status = "stopped" | "playing" | "paused";
export type Voice = "auto" | "piano" | "soft" | "pluck";
/** The actual little synth patches (Voice "auto" resolves to one of these). */
type Patch = PlaybackPatch | "soft" | "pluck";

const SPEEDS = [0.5, 0.75, 1, 1.25];
const LOOKAHEAD_S = 0.25; // schedule notes this far ahead (wall-clock)
const COUNT_IN_BEATS = 4;
const BEAT_S = 0.5; // the exporter's fixed 120 BPM
const NOTE_GAIN = 0.25;

const VOICES: { key: Voice; label: string }[] = [
  { key: "auto", label: "Auto (match instrument)" },
  { key: "piano", label: "Piano-ish" },
  { key: "soft", label: "Soft synth" },
  { key: "pluck", label: "Pluck" },
];

interface ActiveNode {
  oscs: OscillatorNode[];
  gain: GainNode;
  startCtxTime: number;
}

function midiToFreq(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function formatTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const minutes = Math.floor(s / 60);
  const rest = s - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

export default function PlayAlong({
  notes,
  instrumentKey,
  onTick,
  registerSeek,
  autoScroll,
  onAutoScrollChange,
}: PlayAlongProps) {
  const [status, setStatus] = useState<Status>("stopped");
  const [rate, setRate] = useState(1);
  const [countIn, setCountIn] = useState(true);
  const [voice, setVoice] = useState<Voice>("auto");
  const [positionDisplay, setPositionDisplay] = useState(0);

  const ctxRef = useRef<AudioContext | null>(null);
  const anchorCtxTimeRef = useRef(0);
  const anchorPosRef = useRef(0);
  const rateRef = useRef(1);
  const patchRef = useRef<Patch>(patchForInstrument(instrumentKey));

  // Resolve which little synth patch actually sounds: Auto follows the
  // selected instrument; the explicit options behave as before.
  useEffect(() => {
    patchRef.current =
      voice === "auto" ? patchForInstrument(instrumentKey) : voice;
  }, [voice, instrumentKey]);
  const pointerRef = useRef(0);
  const activeNodesRef = useRef<ActiveNode[]>([]);
  const rafRef = useRef<number | null>(null);
  const pausedPosRef = useRef(0);
  // Where a fresh (stopped -> play) start begins; set by click-to-seek.
  const startPosRef = useRef(0);
  const statusRef = useRef<Status>("stopped");
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const duration =
    notes.length > 0
      ? Math.max(...notes.map((n) => n.start_time + n.duration))
      : 0;

  const silenceAll = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const now = ctx.currentTime;
    for (const node of activeNodesRef.current) {
      try {
        node.gain.gain.cancelScheduledValues(now);
        node.gain.gain.setValueAtTime(node.gain.gain.value, now);
        node.gain.gain.linearRampToValueAtTime(0, now + 0.03);
        for (const osc of node.oscs) {
          osc.stop(now + 0.05);
        }
      } catch {
        // node may already have ended
      }
    }
    activeNodesRef.current = [];
  }, []);

  const trackNode = useCallback((node: ActiveNode) => {
    activeNodesRef.current.push(node);
    node.oscs[0].onended = () => {
      activeNodesRef.current = activeNodesRef.current.filter((n) => n !== node);
    };
  }, []);

  /** Short percussive blip used for the count-in clicks. */
  const scheduleClick = useCallback(
    (freq: number, when: number) => {
      const ctx = ctxRef.current;
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, when);
      gain.gain.linearRampToValueAtTime(0.12, when + 0.005);
      gain.gain.linearRampToValueAtTime(0, when + 0.06);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(when);
      osc.stop(when + 0.08);
      trackNode({ oscs: [osc], gain, startCtxTime: when });
    },
    [trackNode]
  );

  /**
   * Softer musical voices. Each is a tiny additive patch through a lowpass
   * filter with a gain envelope — nothing fancy, just not a raw beep.
   * v0.9.1: per-instrument patches (guitar/bass/uke plucks, a breathier
   * "wind" tone for flute/violin/sax/trumpet/clarinet/voice) chosen
   * automatically when the Sound selector is on Auto.
   */
  const scheduleNoteSound = useCallback(
    (freq: number, when: number, wallDuration: number, velocity = 1) => {
      const ctx = ctxRef.current;
      if (!ctx) return;
      // v0.9.3: detected loudness scales the note (floored so quiet chord
      // members stay audible).
      const NOTE_PEAK = NOTE_GAIN * Math.max(0.35, Math.min(1, velocity));
      const patch = patchRef.current;
      const gain = ctx.createGain();
      const filter = ctx.createBiquadFilter();
      filter.type = "lowpass";
      gain.connect(filter);
      filter.connect(ctx.destination);

      const oscs: OscillatorNode[] = [];
      const addOsc = (type: OscillatorType, f: number, level: number) => {
        const osc = ctx.createOscillator();
        osc.type = type;
        osc.frequency.value = f;
        const oscGain = ctx.createGain();
        oscGain.gain.value = level;
        osc.connect(oscGain);
        oscGain.connect(gain);
        osc.start(when);
        osc.stop(when + wallDuration + 0.05);
        oscs.push(osc);
      };

      const end = when + wallDuration;
      const g = gain.gain;
      if (patch === "piano") {
        // Fundamental + quiet octave, percussive attack, decaying body.
        filter.frequency.value = 2600;
        addOsc("triangle", freq, 1);
        addOsc("sine", freq * 2, 0.3);
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_PEAK, when + 0.01);
        g.exponentialRampToValueAtTime(
          Math.max(0.02, NOTE_PEAK * 0.3),
          Math.max(when + 0.02, end - 0.05)
        );
        g.linearRampToValueAtTime(0, end);
      } else if (patch === "soft" || patch === "wind") {
        // Barely-detuned sines, slow attack and release; "wind" adds a
        // whisper of second harmonic for flutes/horns/voice.
        filter.frequency.value = patch === "wind" ? 2100 : 1800;
        addOsc("sine", freq, 0.7);
        addOsc("sine", freq * 1.003, 0.5);
        if (patch === "wind") {
          addOsc("sine", freq * 2, 0.12);
        }
        const attack = Math.min(0.08, wallDuration / 3);
        const release = Math.min(0.1, wallDuration / 3);
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_PEAK, when + attack);
        g.setValueAtTime(NOTE_PEAK, end - release);
        g.linearRampToValueAtTime(0, end);
      } else if (patch === "guitar") {
        // Warm pluck: rounder filter, longer singing decay than raw pluck.
        filter.frequency.value = 1900;
        addOsc("triangle", freq, 1);
        addOsc("sine", freq * 2, 0.25);
        const decay = Math.min(1.1, Math.max(0.35, wallDuration + 0.25));
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_PEAK, when + 0.008);
        g.exponentialRampToValueAtTime(0.012, when + decay);
        g.linearRampToValueAtTime(0, end);
      } else if (patch === "bass") {
        // Deep and soft: mostly fundamental through a dark filter.
        filter.frequency.value = 750;
        addOsc("sine", freq, 1);
        addOsc("triangle", freq, 0.35);
        addOsc("sine", freq * 2, 0.15);
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_PEAK * 1.15, when + 0.012);
        g.exponentialRampToValueAtTime(
          Math.max(0.02, NOTE_PEAK * 0.35),
          Math.max(when + 0.03, end - 0.06)
        );
        g.linearRampToValueAtTime(0, end);
      } else if (patch === "uke") {
        // Light, quick pluck.
        filter.frequency.value = 2600;
        addOsc("triangle", freq, 1);
        addOsc("sine", freq * 2, 0.2);
        const decay = Math.min(0.5, Math.max(0.16, wallDuration * 0.7));
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_PEAK, when + 0.005);
        g.exponentialRampToValueAtTime(0.01, when + decay);
        g.linearRampToValueAtTime(0, end);
      } else {
        // Pluck: fast decay regardless of note length.
        filter.frequency.value = 2200;
        addOsc("triangle", freq, 1);
        const decay = Math.min(0.8, Math.max(0.15, wallDuration));
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_PEAK, when + 0.005);
        g.exponentialRampToValueAtTime(0.008, when + decay);
        g.linearRampToValueAtTime(0, end);
      }

      trackNode({ oscs, gain, startCtxTime: when });
    },
    [trackNode]
  );

  const noteIndexAt = useCallback(
    (position: number): number | null => {
      for (let i = 0; i < notes.length; i++) {
        const n = notes[i];
        if (n.start_time > position) break;
        if (position < n.start_time + n.duration) return i;
      }
      return null;
    },
    [notes]
  );

  const stopLoop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const handleStop = useCallback(() => {
    stopLoop();
    silenceAll();
    pausedPosRef.current = 0;
    startPosRef.current = 0;
    setStatus("stopped");
    setPositionDisplay(0);
    onTick(null, null);
  }, [stopLoop, silenceAll, onTick]);

  // The animation-frame loop calls itself via a ref: the stable `tick`
  // wrapper is what gets scheduled, while the body (assigned in an effect,
  // so it always sees fresh props/state) does the work.
  const tickBodyRef = useRef<() => void>(() => {});
  const tick = useCallback(() => {
    tickBodyRef.current();
  }, []);

  useEffect(() => {
    tickBodyRef.current = () => {
      const ctx = ctxRef.current;
      if (!ctx) return;
      const rawPos =
        anchorPosRef.current +
        (ctx.currentTime - anchorCtxTimeRef.current) * rateRef.current;

      // Schedule upcoming notes inside the lookahead window.
      while (pointerRef.current < notes.length) {
        const note = notes[pointerRef.current];
        const when =
          anchorCtxTimeRef.current +
          (note.start_time - anchorPosRef.current) / rateRef.current;
        if (when > ctx.currentTime + LOOKAHEAD_S) break;
        scheduleNoteSound(
          midiToFreq(note.pitch),
          Math.max(when, ctx.currentTime),
          note.duration / rateRef.current,
          note.velocity ?? 1
        );
        pointerRef.current += 1;
      }

      const pos = Math.max(0, rawPos);
      setPositionDisplay(pos);
      onTick(pos, noteIndexAt(pos));

      if (rawPos >= duration + 0.1) {
        handleStop();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
  }, [notes, duration, scheduleNoteSound, noteIndexAt, onTick, handleStop, tick]);

  /** (Re)start the transport at the given position with the given rate. */
  const startTransport = useCallback(
    (startPos: number, newRate: number, withCountIn: boolean) => {
      const ctx = ctxRef.current;
      if (!ctx) return;
      const now = ctx.currentTime;
      rateRef.current = newRate;
      const beatWall = BEAT_S / newRate;
      const delay = withCountIn ? COUNT_IN_BEATS * beatWall : 0.08;

      if (withCountIn) {
        for (let i = 0; i < COUNT_IN_BEATS; i++) {
          scheduleClick(i === 0 ? 1500 : 1100, now + i * beatWall);
        }
      }

      anchorCtxTimeRef.current = now + delay;
      anchorPosRef.current = startPos;

      // First note fully at/after the start position…
      pointerRef.current = notes.findIndex((n) => n.start_time >= startPos);
      if (pointerRef.current === -1) pointerRef.current = notes.length;
      // …plus the remainder of EVERY note already sounding at that position
      // (v0.9.3: with chords, several notes can be mid-ring at once).
      for (const n of notes) {
        if (n.start_time >= startPos) break;
        const remaining = n.start_time + n.duration - startPos;
        if (remaining > 0.01) {
          scheduleNoteSound(
            midiToFreq(n.pitch),
            anchorCtxTimeRef.current,
            remaining / newRate,
            n.velocity ?? 1
          );
        }
      }

      stopLoop();
      rafRef.current = requestAnimationFrame(tick);
    },
    [notes, scheduleClick, scheduleNoteSound, tick, stopLoop]
  );

  const handlePlayPause = useCallback(() => {
    if (status === "playing") {
      // Pause
      const ctx = ctxRef.current;
      if (ctx) {
        const rawPos =
          anchorPosRef.current +
          (ctx.currentTime - anchorCtxTimeRef.current) * rateRef.current;
        pausedPosRef.current = Math.max(0, Math.min(rawPos, duration));
      }
      stopLoop();
      silenceAll();
      setStatus("paused");
      setPositionDisplay(pausedPosRef.current);
      onTick(pausedPosRef.current, noteIndexAt(pausedPosRef.current));
      return;
    }

    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
    }
    void ctxRef.current.resume();

    const resuming = status === "paused";
    // Fresh starts begin wherever click-to-seek last placed the playhead
    // (0 unless the user clicked while stopped).
    const startPos = resuming ? pausedPosRef.current : startPosRef.current;
    startTransport(startPos, rate, !resuming && countIn);
    setStatus("playing");
  }, [status, rate, countIn, duration, startTransport, stopLoop, silenceAll, onTick, noteIndexAt]);

  const handleRateChange = useCallback(
    (newRate: number) => {
      setRate(newRate);
      if (status !== "playing") {
        rateRef.current = newRate;
        return;
      }
      const ctx = ctxRef.current;
      if (!ctx) return;
      const rawPos =
        anchorPosRef.current +
        (ctx.currentTime - anchorCtxTimeRef.current) * rateRef.current;
      const pos = Math.max(0, Math.min(rawPos, duration));
      silenceAll();
      startTransport(pos, newRate, false);
    },
    [status, duration, silenceAll, startTransport]
  );

  const handleVoiceChange = useCallback((v: Voice) => {
    setVoice(v);
  }, []);

  /** Click-to-seek (v0.9.2): jump the transport/playhead to a position. */
  const handleSeek = useCallback(
    (positionSeconds: number) => {
      const pos = Math.max(0, Math.min(positionSeconds, duration));
      const current = statusRef.current;
      if (current === "playing") {
        silenceAll();
        startTransport(pos, rateRef.current, false);
      } else if (current === "paused") {
        pausedPosRef.current = pos;
      } else {
        startPosRef.current = pos;
      }
      setPositionDisplay(pos);
      onTick(pos, noteIndexAt(pos));
    },
    [duration, silenceAll, startTransport, onTick, noteIndexAt]
  );

  useEffect(() => {
    registerSeek?.(handleSeek);
  }, [registerSeek, handleSeek]);

  // Full cleanup when the component unmounts or the notes change (a note
  // edit mid-playback stops the transport cleanly).
  useEffect(() => {
    return () => {
      stopLoop();
      silenceAll();
      const ctx = ctxRef.current;
      if (ctx) {
        void ctx.close();
        ctxRef.current = null;
      }
    };
  }, [notes, stopLoop, silenceAll]);

  if (notes.length === 0) {
    return null;
  }

  return (
    <section className="rounded border border-gray-300 p-4">
      <h2 className="mb-1 text-lg font-medium">Play Along</h2>
      <p className="mb-3 text-xs text-gray-600">
        Playback uses the generated transcription, not the original audio.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handlePlayPause}
          data-testid="playalong-play"
          className="w-24 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          {status === "playing" ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          onClick={handleStop}
          disabled={status === "stopped"}
          data-testid="playalong-stop"
          className="rounded border border-gray-400 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Stop
        </button>
        <span
          className="font-mono text-sm text-gray-700"
          data-testid="playalong-time"
        >
          {formatTime(positionDisplay)} / {formatTime(duration)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1">
          <span className="mr-1 text-sm text-gray-600">Speed:</span>
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleRateChange(s)}
              data-testid={`playalong-speed-${s * 100}`}
              className={`rounded px-2 py-1 text-sm ${
                rate === s
                  ? "bg-blue-600 font-medium text-white"
                  : "border border-gray-400 hover:bg-gray-50"
              }`}
            >
              {s * 100}%
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          Sound:
          <select
            value={voice}
            onChange={(e) => handleVoiceChange(e.target.value as Voice)}
            data-testid="playalong-voice"
            className="rounded border border-gray-400 px-2 py-1 text-sm"
          >
            {VOICES.map((v) => (
              <option key={v.key} value={v.key}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={countIn}
            onChange={(e) => setCountIn(e.target.checked)}
            data-testid="playalong-countin"
          />
          4-click count-in
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => onAutoScrollChange(e.target.checked)}
            data-testid="playalong-autoscroll"
          />
          Auto-scroll
        </label>
      </div>
    </section>
  );
}
