"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Note } from "@/lib/api";

interface PlayAlongProps {
  notes: Note[];
  /**
   * Called every animation frame while playing (and once on pause/stop) with
   * the transport position in seconds and the index of the sounding note.
   * Both are null when playback is stopped.
   */
  onTick: (position: number | null, noteIndex: number | null) => void;
  autoScroll: boolean;
  onAutoScrollChange: (value: boolean) => void;
}

type Status = "stopped" | "playing" | "paused";
export type Voice = "piano" | "soft" | "pluck";

const SPEEDS = [0.5, 0.75, 1, 1.25];
const LOOKAHEAD_S = 0.25; // schedule notes this far ahead (wall-clock)
const COUNT_IN_BEATS = 4;
const BEAT_S = 0.5; // the exporter's fixed 120 BPM
const NOTE_GAIN = 0.25;

const VOICES: { key: Voice; label: string }[] = [
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
  onTick,
  autoScroll,
  onAutoScrollChange,
}: PlayAlongProps) {
  const [status, setStatus] = useState<Status>("stopped");
  const [rate, setRate] = useState(1);
  const [countIn, setCountIn] = useState(true);
  const [voice, setVoice] = useState<Voice>("piano");
  const [positionDisplay, setPositionDisplay] = useState(0);

  const ctxRef = useRef<AudioContext | null>(null);
  const anchorCtxTimeRef = useRef(0);
  const anchorPosRef = useRef(0);
  const rateRef = useRef(1);
  const voiceRef = useRef<Voice>("piano");
  const pointerRef = useRef(0);
  const activeNodesRef = useRef<ActiveNode[]>([]);
  const rafRef = useRef<number | null>(null);
  const pausedPosRef = useRef(0);

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
   */
  const scheduleNoteSound = useCallback(
    (freq: number, when: number, wallDuration: number) => {
      const ctx = ctxRef.current;
      if (!ctx) return;
      const v = voiceRef.current;
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
      if (v === "piano") {
        // Fundamental + quiet octave, percussive attack, decaying body.
        filter.frequency.value = 2600;
        addOsc("triangle", freq, 1);
        addOsc("sine", freq * 2, 0.3);
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_GAIN, when + 0.01);
        g.exponentialRampToValueAtTime(
          Math.max(0.02, NOTE_GAIN * 0.3),
          Math.max(when + 0.02, end - 0.05)
        );
        g.linearRampToValueAtTime(0, end);
      } else if (v === "soft") {
        // Two barely-detuned sines, slow attack and release.
        filter.frequency.value = 1800;
        addOsc("sine", freq, 0.7);
        addOsc("sine", freq * 1.003, 0.5);
        const attack = Math.min(0.08, wallDuration / 3);
        const release = Math.min(0.1, wallDuration / 3);
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_GAIN, when + attack);
        g.setValueAtTime(NOTE_GAIN, end - release);
        g.linearRampToValueAtTime(0, end);
      } else {
        // Pluck: fast decay regardless of note length.
        filter.frequency.value = 2200;
        addOsc("triangle", freq, 1);
        const decay = Math.min(0.8, Math.max(0.15, wallDuration));
        g.setValueAtTime(0, when);
        g.linearRampToValueAtTime(NOTE_GAIN, when + 0.005);
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
          note.duration / rateRef.current
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
      // …plus the remainder of a note already sounding at that position.
      const partial = noteIndexAt(startPos);
      if (partial !== null && notes[partial].start_time < startPos) {
        const n = notes[partial];
        const remaining = n.start_time + n.duration - startPos;
        scheduleNoteSound(
          midiToFreq(n.pitch),
          anchorCtxTimeRef.current,
          remaining / newRate
        );
      }

      stopLoop();
      rafRef.current = requestAnimationFrame(tick);
    },
    [notes, scheduleClick, scheduleNoteSound, noteIndexAt, tick, stopLoop]
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
    const startPos = resuming ? pausedPosRef.current : 0;
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
    voiceRef.current = v;
  }, []);

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
    <section className="rounded border border-gray-200 p-4">
      <h2 className="mb-1 text-lg font-medium">Play Along</h2>
      <p className="mb-3 text-xs text-gray-500">
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
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
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
                  : "border border-gray-300 hover:bg-gray-50"
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
            className="rounded border border-gray-300 px-2 py-1 text-sm"
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
