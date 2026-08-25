import type { CSSProperties, ReactNode, SVGProps } from 'react';
import './paper-boat.css';

/**
 * Paper boat mark, in three flavours:
 *
 *   <PaperBoatLogo />      static brand mark
 *   <PaperBoatLoader />    full-size loading state
 *   <PaperBoatThinking />  compact inline "assistant is thinking" indicator
 *
 * All three draw the same artwork and inherit `color`, so they take the ink
 * colour of whatever they sit in.
 *
 * The original trace fused the hull with the top wave into a single outline.
 * It is cut here at the two points where they meet: the hull keeps its own
 * bottom edge, and each wave tail is hinged at its cut point and carried by
 * whatever displacement the hull's cut point undergoes — so the joints stay
 * shut no matter how the two parts move. The tails also overshoot the cut by a
 * few units, tucked under the hull, so the shared edge never hairlines.
 */

const VIEW_BOX = '0 0 393.5 245.62';
const WIDTH = 393.5;
const HEIGHT = 245.62;

const HULL = 'M188.64 8.79C187.44 10.39 165.34 45.19 149.14 71.19L139.14 87.29 81.24 87.59C28.64 87.89 23.24 88.09 22.34 89.59 21.44 90.89 22.44 92.59 27.24 98.59 34.54 107.69 79.44 161.69 96.34 181.69 103.14 189.89 108.54 196.79 108.34 197.09L108 206.11C114.02 207.91 119.31 208.95 126.34 209.99 136.54 211.49 138.54 211.49 148.84 210.09 168.44 207.39 176.04 204.39 215.64 183.69 236.14 172.89 250.14 169.59 270.54 170.69 281.94 171.34 288.96 172.72 301 177.15L301.44 168.49 298.74 167.49 306.64 151.39C311.04 142.59 314.64 135.19 314.64 134.99 314.64 134.79 321.64 120.29 330.24 102.79 360.84 40.29 360.34 41.69 353.54 42.09 350.54 42.29 335.04 46.19 315.14 51.79 312.44 52.49 302.94 55.09 294.14 57.39 285.34 59.69 271.74 63.39 263.94 65.49L249.84 69.39 242.44 61.59C238.34 57.39 231.74 50.29 227.64 45.89 223.54 41.49 216.24 33.89 211.54 28.89 206.84 23.99 200.74 17.49 198.14 14.59 192.14 8.09 190.24 6.89 188.64 8.79ZM223.74 50.89C238.24 66.19 252.94 81.69 256.24 85.29L262.44 91.79 256.94 95.09C253.94 96.89 251.44 98.39 251.34 98.39 251.14 98.39 242.94 102.89 233.14 108.39 223.34 113.89 215.14 118.19 214.94 117.99 214.64 117.79 198.14 34.89 196.44 25.09 196.14 23.59 196.24 22.49 196.64 22.59 196.94 22.79 209.14 35.49 223.74 50.89ZM186.34 121.09C185.74 121.59 133.64 110.69 132.84 109.89 132.64 109.69 136.34 103.29 141.14 95.69 145.84 88.09 150.34 80.99 150.94 79.89 151.64 78.79 154.84 73.59 158.24 68.39 161.54 63.19 169.14 50.89 175.24 41.19L186.14 23.49 186.44 72.09C186.54 98.89 186.54 120.89 186.34 121.09ZM197.64 62.89C199.94 74.49 203.44 92.29 205.54 102.69L209.24 121.39 206.04 123.29C203.34 124.89 202.24 124.99 197.84 123.99 195.04 123.39 192.74 122.59 192.74 122.09 192.34 119.09 192.74 41.19 193.14 41.49 193.34 41.79 195.44 51.39 197.64 62.89ZM347.34 53.09C347.04 53.59 345.04 57.69 342.84 62.39 340.64 67.09 334.34 80.09 328.84 91.39 323.34 102.69 313.24 123.49 306.34 137.69 294.24 162.39 293.74 163.39 291.44 162.49 287.64 161.09 211.14 128.29 210.84 127.99 210.74 127.79 223.04 120.79 238.34 112.29 253.64 103.89 267.04 96.39 268.14 95.79 269.24 95.19 278.24 90.19 288.14 84.69 298.04 79.19 308.44 73.39 311.14 71.89 316.74 68.79 332.14 60.29 340.64 55.49 346.14 52.49 348.14 51.69 347.34 53.09ZM328.14 55.29C327.54 55.79 324.64 57.49 321.64 59.19 318.64 60.79 314.34 63.19 312.14 64.39 301.84 70.29 272.04 86.69 270.14 87.59 268.24 88.39 267.14 87.69 261.84 82.19 258.54 78.79 255.74 75.39 255.64 74.89 255.54 74.29 257.44 73.39 259.84 72.79 263.84 71.69 274.14 68.99 297.14 62.79 302.14 61.49 310.84 59.09 316.64 57.49 328.74 54.19 329.44 54.09 328.14 55.29ZM134.64 93.89C134.64 94.29 127.24 106.69 125.94 108.29 125.64 108.69 114.44 106.49 85.64 100.39 77.64 98.69 67.84 96.69 63.74 95.89 59.64 95.09 56.14 94.19 55.84 93.89 55.54 93.59 73.14 93.39 94.94 93.39 116.84 93.39 134.64 93.59 134.64 93.89ZM53.44 99.79C62.64 101.69 76.64 104.69 84.64 106.39 92.64 108.09 103.44 110.29 108.64 111.39 113.84 112.49 124.64 114.69 132.64 116.39 140.64 118.09 149.14 119.89 151.64 120.39 154.14 120.89 162.64 122.69 170.64 124.39 178.64 126.09 187.74 127.99 190.94 128.59 194.04 129.29 196.64 129.99 196.54 130.29 196.54 130.59 186.04 139.49 173.34 150.09 160.54 160.59 142.74 175.39 133.74 182.99L117.34 196.79 111.94 190.69C109.04 187.39 97.54 173.69 86.44 160.19 64.94 134.39 37.34 101.09 34.84 98.09 33.44 96.59 33.54 96.39 35.04 96.39 35.94 96.39 44.24 97.89 53.44 99.79ZM210.74 134.79C213.74 135.99 228.84 142.49 244.34 148.99 259.84 155.49 272.64 161.09 272.64 161.39 272.64 161.69 267.14 161.99 260.34 161.99 239.24 162.29 233.04 164.49 189.14 186.99 182.04 190.69 172.34 194.99 167.64 196.59 153.94 201.29 135.94 203.09 124.84 200.79 122.64 200.39 122.74 200.09 126.94 196.59 133.34 191.29 189.74 143.89 197.04 137.69 200.44 134.89 203.64 132.49 204.24 132.49 204.94 132.39 207.84 133.49 210.74 134.79Z';
const TAIL_L = 'M108.34 197.09C107.74 197.59 98.44 194.49 89.54 190.79 67.74 181.79 50.34 179.29 34.64 182.89 27.14 184.69 13.74 191.09 8.64 195.29 4.94 198.39 5.14 200.79 8.94 198.39 18.24 192.49 30.94 188.39 42.14 187.69 54.94 186.89 64.64 189.09 84.64 197.39 96.65 202.33 104.05 205.09 111 206.96Z';
const TAIL_R = 'M298 176.07C301.53 177.31 305.49 178.82 310.14 180.69 332.94 189.89 336.44 190.79 350.14 190.79 360.14 190.89 363.24 190.49 368.74 188.59 377.34 185.69 388.84 178.29 387.34 176.79 387.14 176.59 383.14 178.09 378.54 180.29 359.24 189.19 346.74 188.29 318.64 175.89 310.64 172.39 302.94 169.09 301.44 168.49Z';
const SWELL = 'M259.64 188.99C246.24 191.39 234.74 195.99 215.14 206.89 182.64 225.09 169.14 229.39 145.64 229.39 128.84 229.29 113.84 225.69 95.44 217.19 80.94 210.39 82.14 213.79 97.64 223.19 106.34 228.39 120.84 234.09 130.34 236.09 139.74 237.89 157.74 238.19 166.64 236.49 182.94 233.49 197.24 227.59 219.04 214.99 240.44 202.59 253.24 197.99 269.24 196.79 281.14 195.79 290.64 197.89 312.64 206.29 325.64 211.29 339.04 212.69 349.04 210.09 356.94 207.99 355.64 206.89 345.94 207.29 334.54 207.69 328.84 206.39 312.94 199.39 293.44 190.69 288.24 189.29 274.14 188.89 267.54 188.69 261.04 188.69 259.64 188.99Z';
const RIPPLE = 'M260.24 206.99C252.04 208.79 243.24 212.99 235.94 218.49 226.94 225.29 229.34 225.89 241.94 219.89 260.84 210.89 275.74 209.29 291.94 214.39 295.74 215.59 299.04 216.29 299.34 215.99 300.24 215.09 292.14 210.49 286.04 208.49 277.44 205.69 268.54 205.09 260.24 206.99Z';

/**
 * The mark is fine line art. Below roughly 130px wide the thinnest strokes fall
 * under a pixel, so a hairline stroke is added back — in CSS px, not user
 * units, so it stays exactly one hairline at any scale.
 */
function inkFor(size: number): number {
  if (size >= 128) return 0;
  if (size >= 88) return 0.4;
  if (size >= 60) return 0.6;
  if (size >= 44) return 0.8;
  return 1;
}

/**
 * The roll is angular and so looks the same at any size, but the heave and sway
 * are measured in the artwork's own units — at 38px they come to a fifth of a
 * pixel and the boat looks frozen. So the smaller the mark, the more motion it
 * gets. The `amplitude` prop scales whatever this returns.
 */
function ampFor(size: number): number {
  if (size >= 96) return 1;
  if (size >= 64) return 1.15;
  if (size >= 44) return 1.35;
  return 1.6;
}

// SVGProps<SVGSVGElement> includes generic presentation/animation attributes
// (e.g. `speed`) whose built-in types collide with these components' own
// number/boolean props of the same name — omit them so our narrower types win.
type MarkOwnKeys = 'size' | 'ink' | 'speed' | 'amplitude' | 'sailing' | 'busy' | 'className' | 'style' | 'children';

interface MarkProps extends Omit<SVGProps<SVGSVGElement>, MarkOwnKeys> {
  size: number;
  ink?: number;
  speed?: number;
  amplitude?: number;
  sailing?: boolean;
  busy?: boolean;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

function Mark({
  size,
  ink,
  speed = 1,
  amplitude = 1,
  sailing = false,
  busy = false,
  className,
  style,
  children,
  ...rest
}: MarkProps) {
  const stroke = ink === undefined ? inkFor(size) : ink;
  const cls = ['pb'];
  if (sailing) cls.push('pb--sailing');
  if (busy) cls.push('pb--busy');
  if (stroke > 0) cls.push('pb--inked');
  if (className) cls.push(className);

  return (
    <svg
      className={cls.join(' ')}
      viewBox={VIEW_BOX}
      width={size}
      height={Math.round((size * HEIGHT) / WIDTH * 100) / 100}
      style={{
        '--pb-ink': stroke,
        '--pb-amp': Math.round(ampFor(size) * amplitude * 100) / 100,
        '--pb-dur': `${(2.6 / speed).toFixed(2)}s`,
        ...style,
      } as CSSProperties}
      {...rest}
    >
      {children}
      <g className="pb-swell">
        <path d={SWELL} />
      </g>
      <g className="pb-ripple">
        <path d={RIPPLE} />
      </g>
      <g className="pb-tail-l">
        <path d={TAIL_L} />
      </g>
      <g className="pb-tail-r">
        <path d={TAIL_R} />
      </g>
      <g className="pb-hull">
        <path d={HULL} fillRule="evenodd" />
      </g>
    </svg>
  );
}

/**
 * Static brand mark. Pass a `title` to expose it to screen readers (use this
 * when the logo is the only thing naming your app); leave it off when the mark
 * sits next to a wordmark, and it stays decorative.
 */
export interface PaperBoatLogoProps extends Omit<SVGProps<SVGSVGElement>, MarkOwnKeys | 'title'> {
  size?: number;
  title?: string;
}

export function PaperBoatLogo({ size = 44, title, ...rest }: PaperBoatLogoProps) {
  return (
    <Mark
      size={size}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
    </Mark>
  );
}

/**
 * Loading state: the boat rides the swell while the water moves under it.
 * `speed` and `amplitude` scale the motion (1 = default).
 */
export interface PaperBoatLoaderProps extends Omit<SVGProps<SVGSVGElement>, MarkOwnKeys | 'label' | 'showLabel'> {
  size?: number;
  speed?: number;
  amplitude?: number;
  label?: string;
  showLabel?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function PaperBoatLoader({
  size = 76,
  speed = 1,
  amplitude = 1,
  label = 'Loading…',
  showLabel = false,
  className,
  style,
  ...rest
}: PaperBoatLoaderProps) {
  return (
    <span
      className={['pb-status', className].filter(Boolean).join(' ')}
      style={style}
      role="status"
      aria-live="polite"
    >
      <Mark
        size={size}
        speed={speed}
        amplitude={amplitude}
        sailing
        busy
        aria-hidden="true"
        {...rest}
      />
      {showLabel ? (
        <span className="pb-status__label">{label}</span>
      ) : (
        <span className="pb-sr">{label}</span>
      )}
    </span>
  );
}

/**
 * Chat "thinking" indicator: same boat, calmer water, sized to sit on a line of
 * text. Drop it in the assistant bubble while a reply is streaming.
 */
export interface PaperBoatThinkingProps extends Omit<SVGProps<SVGSVGElement>, MarkOwnKeys | 'label' | 'showLabel'> {
  size?: number;
  speed?: number;
  amplitude?: number;
  label?: string;
  showLabel?: boolean;
  /**
   * Animated ellipsis after the label. On by default.
   *
   * Turn it off where the sailing mark already carries the motion: two
   * animations running at different tempos next to each other read as two
   * separate things happening, and the eye follows the faster one — which is
   * the ellipsis, the half with nothing to say.
   */
  showDots?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function PaperBoatThinking({
  size = 38,
  speed = 0.72,
  amplitude = 0.85,
  label = 'Thinking',
  showLabel = true,
  showDots = true,
  className,
  style,
  ...rest
}: PaperBoatThinkingProps) {
  return (
    <span
      className={['pb-status', className].filter(Boolean).join(' ')}
      style={style}
      role="status"
      aria-live="polite"
    >
      <Mark
        size={size}
        speed={speed}
        amplitude={amplitude}
        sailing
        busy
        aria-hidden="true"
        {...rest}
      />
      {showLabel ? (
        <span className="pb-status__label">
          {label}
          {showDots ? (
            <span className="pb-dots" aria-hidden="true">
              <i>.</i>
              <i>.</i>
              <i>.</i>
            </span>
          ) : null}
        </span>
      ) : (
        <span className="pb-sr">{label}</span>
      )}
    </span>
  );
}

export default PaperBoatLogo;
