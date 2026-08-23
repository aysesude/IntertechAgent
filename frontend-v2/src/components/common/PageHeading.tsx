import type { ReactNode } from "react";

interface PageHeadingProps {
  kicker: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeading({ kicker, title, description, actions }: PageHeadingProps) {
  return (
    <div className="mb-6 flex flex-col items-start gap-5 sm:mb-7 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-8">
      <div>
        <div className="font-display mb-2.5 text-xs font-semibold uppercase tracking-[1.4px] text-navy">{kicker}</div>
        <h1 className="font-display m-0 mb-2 text-[26px] font-bold tracking-[-1px] sm:text-[32px] lg:text-[38px]">{title}</h1>
        {description && <p className="m-0 max-w-2xl text-[14px] text-ink-muted sm:text-[15px]">{description}</p>}
      </div>
      {actions && <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">{actions}</div>}
    </div>
  );
}
