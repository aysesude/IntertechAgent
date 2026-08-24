# Paper boat mark

The hand-drawn boat, as a static logo and as two animated states — a loading
spinner and a chat "thinking" indicator — where the boat rides the swell and the
water moves under it.

```
paper-boat/
  PaperBoat.jsx     three React components
  paper-boat.css    geometry-dependent styles + the motion keyframes
  paper-boat.svg    the static mark as a standalone file (favicon, <img>, email)
  preview.html      open in a browser to see every state; no build step
```

## Drop it in

Copy the folder into your React app (e.g. `src/components/paper-boat/`) and
import what you need. `PaperBoat.jsx` imports its own CSS, so any bundler with
CSS support (Vite, CRA, Next, Parcel) needs nothing else.

```jsx
import { PaperBoatLogo, PaperBoatLoader, PaperBoatThinking }
  from './components/paper-boat/PaperBoat';
```

For a TypeScript project, rename it to `PaperBoat.tsx` — the file is plain JSX
with no annotations, so it compiles as-is.

## Components

### `<PaperBoatLogo />`

```jsx
<PaperBoatLogo size={44} />                       {/* decorative */}
<PaperBoatLogo size={120} title="Acme" />         {/* names the app */}
<PaperBoatLogo size={64} style={{ color: '#1d4ed8' }} />
```

| prop | default | |
|---|---|---|
| `size` | `44` | width in px; height follows the artwork's ratio |
| `title` | — | when set, the mark becomes `role="img"` with this label; when absent it is `aria-hidden` |
| `ink` | auto | override the hairline stroke (see *Small sizes*) |

### `<PaperBoatLoader />`

```jsx
<PaperBoatLoader />
<PaperBoatLoader size={120} speed={1.4} showLabel label="Loading your trips…" />
```

| prop | default | |
|---|---|---|
| `size` | `76` | |
| `speed` | `1` | `2` = twice as fast |
| `amplitude` | `1` | multiplies the movement — `0.5` = half, `0` = still |
| `label` | `'Loading…'` | |
| `showLabel` | `false` | when false the label is still announced, just visually hidden |

Wrapped in `role="status" aria-live="polite"`, so screen readers announce it
when it appears.

### `<PaperBoatThinking />`

Sized and paced for a chat bubble: same boat, calmer water, animated ellipsis.

```jsx
{isStreaming && <PaperBoatThinking />}
<PaperBoatThinking size={32} label="Searching" />
<PaperBoatThinking showLabel={false} />
<PaperBoatThinking label="Thinking" showDots={false} />
```

Same props as the loader, with `size: 38`, `speed: 0.72`, `amplitude: 0.85` and
`showLabel: true` as defaults, plus `showDots: true`.

Set `showDots={false}` where the sailing mark is meant to be the only motion:
two animations at different tempos side by side read as two separate things,
and the eye follows the faster one.

## Colour

Everything is filled with `currentColor`, so the mark takes the ink colour of
whatever it sits in — including on a dark background or inside a filled button.
Set `color` on the component or on any ancestor.

The one exception is `paper-boat.svg` loaded through `<img src>`: that document
is isolated from the page, so `currentColor` falls back to black. Inline the SVG
(or use it as a CSS `mask`) if you need it to follow the theme.

## Small sizes

The mark is fine line art. Below about 128px wide its thinnest strokes drop under
one pixel, so a hairline stroke is painted back on — in CSS px via
`vector-effect: non-scaling-stroke`, so it stays exactly one hairline no matter
the scale. That is the `ink` prop, automatic by default.

Below ~32px the counters close up and it turns into a blob. For favicons and
avatars at that size, draw a simplified mark (hull and one sail, no waves)
rather than scaling this one down.

Motion is size-aware for the same reason. The roll is angular and reads the same
at any scale, but the heave and sway are in the artwork's own units — at 38px
they work out to a fifth of a pixel. So smaller marks get a larger base
amplitude, and the `amplitude` prop multiplies that.

## Tuning the motion

Two CSS custom properties drive everything; `speed` and `amplitude` just set
them, and you can also set them from your own CSS:

```css
.my-slow-boat { --pb-dur: 4s; --pb-amp: 0.6; }
```

Under `prefers-reduced-motion: reduce` all movement stops and the busy states
fade gently instead, so they still read as "working".

## How the artwork is put together

The original trace is one outline in which the hull and the top wave are fused —
the boat's bottom edge *is* the wave. It was cut at the two points where they
meet, so:

- the **hull** keeps that bottom edge and moves as a rigid body (roll, heave, a
  little sway);
- each **wave tail** is hinged at its cut point and translated by whatever
  displacement the hull's cut point undergoes, so the joint cannot open however
  far the two parts move apart;
- each tail also overshoots its cut by a few units, tucked under the hull, so the
  shared edge never shows a hairline;
- the two **lower waves** were already separate strokes and drift on their own,
  off-cycle durations so the water never repeats in visible lockstep.

The rotation origins in `paper-boat.css` are real points in the artwork's
coordinate system, and `transform-box: view-box` measures from the viewBox's
min-x/min-y — so **the viewBox must keep starting at `0 0`**. Padding for the
movement is baked into the path coordinates rather than into a negative viewBox
origin.

`../tools/` holds the scripts that produced the geometry and keyframes, if you
ever want to re-tune the amplitudes and rebuild.
