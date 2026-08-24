import type { HTMLAttributes } from "react";

/**
 * "Premium glass panel" yüzey stili — arka plan, kenarlık, blur ve gölge.
 * Card burada tek tüketicisi değil: NewsFeed.tsx aynı görünümü Card'ı
 * sarmalamadan (kendi `<article>` etiketiyle) kullanıyor, bu yüzden stil
 * buradan dışa aktarılıyor — iki kopya elle birbirinden ayrışmasın diye.
 * Padding kasıtlı olarak DIŞARIDA tutuldu: her tüketici kendi padding'ini
 * ekliyor (Card p-6, NewsFeed p-[22px]).
 */
export const CARD_SURFACE_CLASS =
  "rounded-xl border border-[rgba(15,23,42,0.08)] bg-white/[0.55] backdrop-blur-[16px] shadow-[0_10px_30px_-20px_rgba(15,23,42,0.12)] transition-[box-shadow,border-color] hover:border-[rgba(15,23,42,0.14)] dark:border-white/[0.08] dark:bg-[#07111c]/[0.82] dark:shadow-[0_10px_30px_-18px_rgba(0,0,0,0.55)] dark:hover:border-white/[0.14]";

export function Card({ className = "", ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`${CARD_SURFACE_CLASS} p-6 ${className}`}
      {...rest}
    />
  );
}
