import { useEffect, useRef, useState } from "react";

export type Easing = (t: number) => number;

export const easeInOutCubic: Easing = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutCubic: Easing = (t) => 1 - Math.pow(1 - t, 3);

/**
 * 0'dan hedef değere kadar sayan animasyon. `delayMs` ile satırlar arasında
 * kademeli (staggered) başlangıç sağlanabilir.
 */
export function useCountUp(target: number, delayMs = 0, durationMs = 950, easing: Easing = easeInOutCubic): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number>();

  useEffect(() => {
    setValue(0);
    const timeout = setTimeout(() => {
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / durationMs);
        setValue(target * easing(t));
        if (t < 1) rafRef.current = requestAnimationFrame(step);
        else setValue(target);
      };
      rafRef.current = requestAnimationFrame(step);
    }, delayMs);

    return () => {
      clearTimeout(timeout);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, delayMs, durationMs, easing]);

  return value;
}
