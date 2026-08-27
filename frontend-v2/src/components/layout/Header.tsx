import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Sun, Moon } from "lucide-react";
import type { ScreenId, User } from "@/types/finance";
import { MenuIcon, XIcon } from "@/components/icons";
import { MaterialIcon } from "@/components/common/MaterialIcon";
import { useTheme } from "@/context/ThemeContext";

const NAV_ITEMS: { id: ScreenId; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "villa" },
  { id: "portfolio", label: "Portfolio", icon: "finance_mode" },
  { id: "market", label: "Market", icon: "payments" },
  { id: "risk", label: "Risk", icon: "crisis_alert" },
  { id: "chat", label: "AI Chat", icon: "explore" },
];

interface HeaderProps {
  user: User;
  activeScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
  /** Oturumu kapatır (AuthContext.logout). */
  onLogout?: () => void;
}

export function Header({ user, activeScreen, onNavigate, onLogout }: HeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const mobileNavRef = useRef<HTMLDivElement>(null);
  const shouldReduceMotion = useReducedMotion();
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuOpen && menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
      if (mobileNavOpen && mobileNavRef.current && !mobileNavRef.current.contains(e.target as Node)) {
        setMobileNavOpen(false);
      }
    }
    document.addEventListener("click", handleClick, true);
    return () => document.removeEventListener("click", handleClick, true);
  }, [menuOpen, mobileNavOpen]);

  return (
    <motion.header
      initial={shouldReduceMotion ? false : { opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      className="sticky top-0 z-[100] border-b border-line bg-white/92 backdrop-blur-md dark:border-transparent dark:bg-[#0D0A0C]/50 dark:backdrop-blur-xl"
    >
      <div className="relative mx-auto flex h-16 max-w-[1440px] items-center gap-3 px-4 sm:h-[68px] sm:px-6 md:px-10 lg:gap-11">
        <button
          type="button"
          onClick={() => onNavigate("dashboard")}
          aria-label="Dashboard'a git"
          className="flex items-center gap-[11px] rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {/* vira_logo_text.svg zaten gemi + "Vira" yazısını birlikte
              içeren tam lockup — ayrıca vira_logo.svg eklemeye gerek yok
              (eklenirse gemi iki kere görünür). */}
          <img
            src="/vira_logo_text.svg"
            alt="VİRA"
            className="block h-8 object-contain dark:[filter:brightness(0)_invert(1)]"
          />
        </button>

        {/* Sol (logo) ve sağ (bildirim/kullanıcı) bloklar farklı genişlikte
            olduğu için flex-1 içinde justify-center kullanmak nav'ı sayfanın
            gerçek ortasından kaydırıyordu — absolute + left-1/2 ile bu
            container'ın (mx-auto max-w-[1440px], sayfanın hiza referansı)
            tam yatay merkezine sabitlendi, sol/sağ blokların genişliğinden
            bağımsız. */}
        <nav className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 lg:block">
          <div className="flex items-center gap-1 rounded-full bg-line2 p-1 dark:bg-white/5">
            {NAV_ITEMS.map((item) => {
              // Al/Sat gezinmede ayrı bir madde DEĞİL, portföyün alt
              // sayfası — oradayken Portfolio vurgulu kalır. Aksi halde
              // hiçbir madde yanmaz ve kullanıcı nerede olduğunu gezinmeden
              // okuyamaz.
              const active =
                item.id === activeScreen ||
                (activeScreen === "trade" && item.id === "portfolio");
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={
                    "group relative whitespace-nowrap rounded-full px-4 py-1.5 text-sm transition-colors " +
                    (active
                      ? "font-semibold text-brand dark:text-[#EB5265]"
                      : "font-medium text-ink-muted hover:text-ink")
                  }
                >
                  {active && (
                    <motion.span
                      layoutId="nav-active-pill"
                      className="absolute inset-0 rounded-full bg-white shadow-card dark:bg-brand-tint"
                      transition={shouldReduceMotion ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 35 }}
                    />
                  )}
                  <span className="relative z-10 inline-flex items-center">
                    <span
                      className={
                        "inline-block overflow-hidden transition-all duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] " +
                        (active
                          ? "mr-1.5 max-w-[20px] opacity-100"
                          : "max-w-0 opacity-0 group-hover:mr-1.5 group-hover:max-w-[20px] group-hover:opacity-100")
                      }
                    >
                      <MaterialIcon name={item.icon} size={16} className="shrink-0" />
                    </span>
                    {item.label}
                  </span>
                </button>
              );
            })}
          </div>
        </nav>

        <div className="relative ml-auto lg:hidden" ref={mobileNavRef}>
          <button
            onClick={() => setMobileNavOpen((v) => !v)}
            aria-label={mobileNavOpen ? "Menüyü kapat" : "Menüyü aç"}
            aria-expanded={mobileNavOpen}
            className="grid h-11 w-11 place-items-center rounded-[10px] border border-line bg-white text-ink-muted transition-colors hover:border-brand hover:bg-brand-tint dark:border-transparent dark:bg-surface-elevated"
          >
            {mobileNavOpen ? <XIcon size={20} /> : <MenuIcon size={20} />}
          </button>

          {mobileNavOpen && (
            <div className="animate-tipIn absolute right-0 top-[calc(100%+10px)] w-[230px] overflow-hidden rounded-xl border border-line bg-white p-1.5 shadow-pop dark:border-transparent dark:bg-surface-elevated">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onNavigate(item.id);
                    setMobileNavOpen(false);
                  }}
                  className={
                    "flex min-h-[44px] w-full items-center rounded-lg px-3 py-2.5 text-left text-sm transition-colors " +
                    (item.id === activeScreen
                      ? "bg-brand-tint font-semibold text-brand"
                      : "font-medium text-ink-muted hover:bg-brand-tint hover:text-brand")
                  }
                >
                  <span className="mr-1.5 inline-flex align-middle">
                    <MaterialIcon name={item.icon} size={16} />
                  </span>
                  {item.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2.5 sm:gap-3.5">
          <button
            onClick={() => setTheme(isDark ? "light" : "dark")}
            aria-label={isDark ? "Açık temaya geç" : "Koyu temaya geç"}
            className="grid h-11 w-11 place-items-center rounded-[10px] border border-line bg-white text-ink-muted transition-colors hover:border-brand hover:bg-brand-tint dark:border-transparent dark:bg-surface-elevated"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>

          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex min-h-[44px] cursor-pointer items-center gap-2.5"
            >
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-[10px] bg-brand text-[13px] font-bold text-white dark:bg-cta-dark">
                {user.initials}
              </div>
              <div className="hidden text-left leading-[1.25] md:block">
                <div className="text-[13px] font-semibold">{user.name}</div>
                <div className="text-[11px] text-ink-soft dark:text-ink-faint">{user.role}</div>
              </div>
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-[calc(100%+10px)] w-[230px] animate-tipIn overflow-hidden rounded-xl border border-line bg-white shadow-pop dark:border-transparent dark:bg-surface-elevated">
                <div className="border-b border-line2 px-4 py-3.5 dark:border-transparent">
                  <div className="text-[13.5px] font-semibold">{user.name}</div>
                  <div className="mt-0.5 text-[11.5px] text-ink-soft dark:text-ink-faint">{user.role}</div>
                </div>
                <div className="p-1.5">
                  {["Hesap Ayarları", "Yardım Merkezi", "Gizlilik ve Kullanım Koşulları"].map((label) => (
                    <a
                      key={label}
                      href="#"
                      className="flex min-h-[44px] items-center rounded-lg px-2.5 text-[13px] text-ink-soft transition-colors hover:bg-brand-tint hover:text-brand"
                    >
                      {label}
                    </a>
                  ))}
                </div>
                <div className="mx-1.5 h-px bg-line2" />
                <div className="p-1.5">
                  {/* <a href="#"> değil <button>: bu bir gezinme değil bir
                      eylem. Bağlantı olarak bırakılsaydı orta tıkla yeni
                      sekmede açılabilir ve hiçbir şey yapmazdı. */}
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      onLogout?.();
                    }}
                    className="flex min-h-[44px] w-full items-center rounded-lg px-2.5 text-left text-[13px] font-semibold text-danger transition-colors hover:bg-danger-tint"
                  >
                    Çıkış Yap
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.header>
  );
}
