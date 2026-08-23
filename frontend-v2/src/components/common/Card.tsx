import type { HTMLAttributes } from "react";

export function Card({ className = "", ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-xl border border-line bg-white/[0.72] p-6 backdrop-blur-2xl transition-shadow hover:shadow-card dark:border-transparent dark:bg-[#0B151E]/[0.92] dark:shadow-[0_8px_28px_-18px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.03)] ${className}`}
      {...rest}
    />
  );
}
