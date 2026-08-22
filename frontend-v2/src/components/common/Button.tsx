import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  icon?: ReactNode;
  loading?: boolean;
}

export function Button({ variant = "primary", icon, loading = false, className = "", children, disabled, ...rest }: ButtonProps) {
  const base =
    "h-[46px] px-5 rounded-[10px] text-sm font-semibold inline-flex items-center gap-2 transition-transform duration-150 hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100";
  const styles =
    variant === "primary"
      ? "bg-brand text-white shadow-[0_2px_10px_rgba(37,87,232,.22)] hover:bg-brand-dark dark:bg-cta-dark dark:shadow-[0_2px_10px_rgba(122,43,57,.35)] dark:hover:bg-[#8E3446] dark:focus-visible:outline-none dark:focus-visible:ring-4 dark:focus-visible:ring-[#8E3446]/40"
      : "bg-white text-brand border-[1.5px] border-brand hover:bg-brand-tint dark:bg-surface-elevated dark:border-white/12";

  return (
    <button className={`${base} ${styles} ${className}`} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 size={17} className="animate-spin" /> : icon}
      {children}
    </button>
  );
}
