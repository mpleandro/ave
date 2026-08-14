/**
 * EDITORIAL caption style — selected with `captions.style: "editorial"`.
 *
 * Look: a LEFT-anchored block of 2-3 short lines where each word carries a role.
 * A connective sits dimmed in blue-light; a content word is bold offwhite; the
 * accent of the phrase is Libre Baskerville italic in orange; a closing word
 * blooms out of blur; a figure explodes in oversized. That contrast IS the style
 * — paint every word the same and it collapses into ordinary subtitles.
 *
 * It is the site's `.amber` pattern moved to video: serif italic in --laranja for
 * the emphasis, dimmed connectives around it. Same two faces, same easing-mãe.
 *
 * Identity comes from ../public/brand.json (the brand preset), NOT from constants
 * here: palette, the two font families, the per-role size/weight/colour table and
 * the motion vocabulary all live there, so a caption, a headline and an SVG b-roll
 * can share one source of truth. `captions.accent` in edit-data.json overrides the
 * brand accent for a single video (that is what the Estilo tab writes).
 *
 * Data: ../public/caption-editorial.json (helpers/caption_style_editorial.py),
 * which assigns the role AND the entry animation per word. Immutable code,
 * data-driven — same contract as Main.tsx.
 */
import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont as loadOpenSans} from '@remotion/google-fonts/OpenSans';
import {loadFont as loadBaskerville} from '@remotion/google-fonts/LibreBaskerville';
import cues from '../public/caption-editorial.json';
import brand from '../public/brand.json';
import editData from '../public/edit-data.json';

// The Avelin faces themselves — Open Sans and Libre Baskerville, straight from
// the site's font link. The serif is only ever 400; its italic IS the emphasis.
const openSans = loadOpenSans('normal', {weights: ['400', '600', '700']});
const SANS = openSans.fontFamily;
const baskerville = loadBaskerville('italic', {weights: ['400']});
const SERIF = baskerville.fontFamily;

type RoleName = 'ctx' | 'stress' | 'serif' | 'serifAcc' | 'punch' | 'num';
type AnimName = 'fade' | 'serifIn' | 'type' | 'pop' | 'glow';
type Word = {text: string; role: RoleName; anim: AnimName; fromMs: number; toMs: number};
type CueData = {i: number; startMs: number; endMs: number; exit: string; lines: Word[][]};

type RoleSpec = {font: 'sans' | 'serif'; weight?: string; color: string; em: number};
type Brand = {
  palette: Record<string, string>;
  roles: Record<string, RoleSpec>;
  motion: Record<string, any>;
  layout: {safeLeftPx: number; lineHeight: number; letterSpacing: number};
  graphics: {captionShadow: string};
};
const B = brand as unknown as Brand;
const M = B.motion;
const L = B.layout;

type CapCfg = {
  fontSize?: number;
  accent?: string;
  editorialOffsetY?: number;
  fontScale?: number;
  windows?: {start: number; end: number; paddingBottom?: number; editorialOffsetY?: number}[];
};
const CAP = ((editData as {captions?: CapCfg}).captions ?? {}) as CapCfg;

// A per-video accent beats the brand default; everything else stays branded.
const ACCENT = CAP.accent ?? B.palette.accent;
const PALETTE: Record<string, string> = {...B.palette, accent: ACCENT};

const BASE_SIZE = (CAP.fontSize ?? 76) * (CAP.fontScale ?? 1);
const OFFSET_Y = CAP.editorialOffsetY ?? 0.2; // block centre, fraction of height
const WINDOWS = CAP.windows ?? [];

const ease = (name: string) => {
  const e = M.ease[name];
  return e ? Easing.bezier(e[0], e[1], e[2], e[3]) : Easing.linear;
};
const EASE_OUT = ease('out');
const EASE_DEC = ease('dec');

// Night-blue tint, not black — the site's whole elevation language is
// rgba(13,33,55,.x), and a black shadow reads as a different brand up close.
const SHADOW = `drop-shadow(${B.graphics.captionShadow})`;

const roleStyle = (role: RoleName): React.CSSProperties => {
  const r = B.roles[role];
  return {
    fontFamily: r.font === 'serif' ? SERIF : SANS,
    fontStyle: r.font === 'serif' ? 'italic' : 'normal',
    fontWeight: r.weight ? Number(r.weight) : 400,
    color: PALETTE[r.color] ?? r.color,
    fontSize: BASE_SIZE * r.em,
  };
};

/** 0 → 1 progress of an entry that begins at `startF` and runs `durSec`. */
const prog = (frame: number, startF: number, durSec: number, fps: number, easing: (n: number) => number) =>
  interpolate(frame, [startF, startF + Math.max(1, durSec * fps)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });

/** One word, animated by the entry its role was assigned. */
const AnimWord: React.FC<{w: Word; startF: number}> = ({w, startF}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const base = roleStyle(w.role);
  const spacing = L.letterSpacing;

  // The typewriter is the one entry that animates below the word — it needs the
  // characters split, so it cannot share the wrapper the other four use.
  if (w.anim === 'type') {
    const chars = Array.from(w.text);
    const stagger = M.type.staggerPerChar * fps;
    return (
      <span style={{...base, letterSpacing: `${spacing}em`, whiteSpace: 'pre', filter: SHADOW}}>
        {chars.map((c, i) => {
          const p = prog(frame, startF + i * stagger, M.type.dur, fps, Easing.linear);
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                opacity: p,
                transform: `translateY(${(1 - p) * M.type.riseY}px)`,
                whiteSpace: 'pre',
              }}
            >
              {c === ' ' ? ' ' : c}
            </span>
          );
        })}
      </span>
    );
  }

  let opacity = 1;
  let transform = '';
  let filter = SHADOW;
  let letterSpacing = `${spacing}em`;

  if (w.anim === 'fade') {
    const p = prog(frame, startF, M.fade.dur, fps, EASE_OUT);
    opacity = p;
    filter = `blur(${(1 - p) * M.fade.blur}px) ${SHADOW}`;
  } else if (w.anim === 'serifIn') {
    const p = prog(frame, startF, M.serifIn.dur, fps, EASE_OUT);
    opacity = p;
    transform = `scale(${interpolate(p, [0, 1], [M.serifIn.scale, 1])})`;
  } else if (w.anim === 'pop') {
    const p = prog(frame, startF, M.pop.dur, fps, EASE_DEC);
    opacity = interpolate(p, [0, 0.35, 1], [0, 1, 1], {extrapolateRight: 'clamp'});
    transform = `scale(${interpolate(p, [0, 1], [M.pop.scale, 1])})`;
    filter = `blur(${(1 - p) * M.pop.blur}px) ${SHADOW}`;
    letterSpacing = `${interpolate(p, [0, 1], [M.pop.tracking, spacing])}em`;
  } else if (w.anim === 'glow') {
    const p = prog(frame, startF, M.glow.dur, fps, EASE_OUT);
    opacity = p;
    transform = `scale(${interpolate(p, [0, 1], [M.glow.scale, 1])})`;
    filter = `blur(${(1 - p) * M.glow.blur}px) ${SHADOW}`;
  }

  return (
    <span
      style={{
        ...base,
        display: 'inline-block',
        transformOrigin: 'left center',
        whiteSpace: 'pre',
        opacity,
        transform,
        filter,
        letterSpacing,
        // the punch keeps a soft bloom in the accent after it has landed
        textShadow:
          w.anim === 'glow'
            ? `0 0 ${M.glow.shadowPx}px ${ACCENT}${Math.round(
                interpolate(prog(frame, startF, M.glow.dur, fps, EASE_OUT), [0, 1], [255, 90]),
              )
                .toString(16)
                .padStart(2, '0')}`
            : undefined,
      }}
    >
      {w.text}
    </span>
  );
};

const Cue: React.FC<{cue: CueData; durFrames: number}> = ({cue, durFrames}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();

  // captions.windows moves the block for part of the video — the split-screen
  // styles park it on the seam. Matched on the ABSOLUTE frame, because inside a
  // Sequence useCurrentFrame() is already local to the cue.
  const absFrame = Math.round((cue.startMs / 1000) * fps) + frame;
  const win = WINDOWS.find(
    (w) => absFrame >= Math.round(w.start * fps) + 1 && absFrame < Math.round(w.end * fps) + 1,
  );
  const offsetY = win
    ? win.editorialOffsetY ??
      (win.paddingBottom != null ? (height - win.paddingBottom - height / 2) / height : OFFSET_Y)
    : OFFSET_Y;

  // Whisper stamps the first word of an incoming take BEFORE the previous word
  // ends at a J-cut seam. Left alone that plays the line out of order, so the
  // reveal is forced monotonic.
  let prevF = -1;
  const startFrames: number[][] = cue.lines.map((ln) =>
    ln.map((w) => {
      const f = Math.max(0, ((w.fromMs - cue.startMs) / 1000) * fps);
      prevF = Math.max(prevF + 0.001, f);
      return prevF;
    }),
  );

  const fadeOutF = Math.max(1, M.fade.dur * fps);
  const exit =
    cue.exit === 'fade'
      ? interpolate(frame, [durFrames - fadeOutF, durFrames], [1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
      : 1;

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'flex-start',
        paddingLeft: L.safeLeftPx,
        paddingRight: L.safeLeftPx,
        top: `${(offsetY - 0.5) * 100}%`,
        opacity: exit,
      }}
    >
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-start'}}>
        {cue.lines.map((ln, li) => {
          // lineHeight 1.0 makes the line box exactly the font size, so the
          // ascenders and descenders of the garamond italic — and any oversized
          // `num` — spill out of it and collide with the line below. Measured on
          // a real render: "ferramenta" sat on top of "gratuita". The leading has
          // to come from a margin scaled by THIS line's largest role rather than
          // from a constant, because a 2.1em figure needs twice the room a 1em
          // word does.
          const maxEm = Math.max(...ln.map((w) => B.roles[w.role].em));
          return (
            <div
              key={li}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: BASE_SIZE * 0.22,
                lineHeight: L.lineHeight,
                marginTop: li === 0 ? 0 : maxEm * BASE_SIZE * 0.2,
              }}
            >
              {ln.map((w, wi) => (
                <AnimWord key={wi} w={w} startF={startFrames[li][wi]} />
              ))}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const EditorialCaptions: React.FC = () => {
  const {fps, durationInFrames} = useVideoConfig();
  const CUES = cues as unknown as CueData[];
  return (
    <AbsoluteFill>
      {CUES.map((cue) => {
        const from = Math.round((cue.startMs / 1000) * fps);
        const to = Math.round((cue.endMs / 1000) * fps);
        const dur = Math.max(1, Math.min(to, durationInFrames) - from);
        if (from >= durationInFrames || dur <= 0) return null;
        return (
          <Sequence key={cue.i} from={from} durationInFrames={dur} layout="none">
            <Cue cue={cue} durFrames={dur} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
