import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base(props: IconProps, children: ReactNode, strokeWidth = 2.2) {
  const { size = 18, ...rest } = props;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const TrendUpIcon = (p: IconProps) => base(p, <path d="M5 15l7-7 7 7" />);
export const TrendDownIcon = (p: IconProps) => base(p, <path d="M5 9l7 7 7-7" />);
export const BellIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>
  ));
export const RefreshIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 4v5h-5" />
    </>
  ));
export const FileTextIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M14 3v5h5" />
      <path d="M15 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z" />
      <path d="M9 13h6M9 17h4" />
    </>
  ));
export const SparkleIcon = (p: IconProps) => base(p, <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />);
export const StocksIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M3 3v18h18" />
      <path d="M7 15l4-5 3 3 5-7" />
    </>
  ));
export const GoldIcon = (p: IconProps) => base(p, <path d="M12 3l7 4v10l-7 4-7-4V7z" />);
export const FxIcon = (p: IconProps) =>
  base(p, (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18" />
    </>
  ));
export const BondIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M4 6h16v12H4z" />
      <path d="M8 10h8M8 14h5" />
    </>
  ));
export const CryptoIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M12 2l8 4.5v11L12 22l-8-4.5v-11z" />
      <path d="M12 8v8M9 10.5h4.5a1.75 1.75 0 0 1 0 3.5H9m0-3.5v3.5m0-3.5V9m0 8v-1.5" />
    </>
  ));
export const CashIcon = (p: IconProps) =>
  base(p, (
    <>
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <circle cx="12" cy="12" r="3" />
      <path d="M6 9h.01M18 15h.01" />
    </>
  ));
export const SendIcon = (p: IconProps) =>
  base(p, (
    <>
      <path d="M22 2 11 13" />
      <path d="M22 2l-7 20-4-9-9-4z" />
    </>
  ));
export const PlusIcon = (p: IconProps) => base(p, <path d="M12 5v14M5 12h14" />);
export const DownloadIcon = (p: IconProps) =>
  base(p, <path d="M12 3v12M7 11l5 5 5-5M4 20h16" />);
export const XIcon = (p: IconProps) => base(p, <path d="M18 6 6 18M6 6l12 12" />);
export const ArrowUpIcon = (p: IconProps) => base(p, <path d="M12 19V5M5 12l7-7 7 7" />);
export const ArrowDownIcon = (p: IconProps) => base(p, <path d="M12 5v14M5 12l7 7 7-7" />);
export const MinusIcon = (p: IconProps) => base(p, <path d="M4 12h16" />);
export const MenuIcon = (p: IconProps) => base(p, <path d="M4 7h16M4 12h16M4 17h16" />);

export const BotIcon = (p: IconProps) => {
  const { size = 22, ...rest } = p;
  return (
    <svg width={size} height={size} viewBox="0 0 30 26" fill="none" {...rest}>
      <rect x="5" y="4" width="20" height="17" rx="9" fill="currentColor" />
      <circle cx="11.5" cy="12" r="1.8" fill="#fff" />
      <circle cx="18.5" cy="12" r="1.8" fill="#fff" />
      <path d="M11 16.5c1 1.1 6 1.1 7 0" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="24" cy="4" r="4.2" fill="currentColor" />
      <circle cx="22.6" cy="4" r=".7" fill="#fff" />
      <circle cx="24" cy="4" r=".7" fill="#fff" />
      <circle cx="25.4" cy="4" r=".7" fill="#fff" />
    </svg>
  );
};
