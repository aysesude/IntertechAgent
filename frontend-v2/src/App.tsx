import { useEffect, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { BackgroundLayer } from "@/components/BackgroundLayer";
import { Header } from "@/components/layout/Header";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { DashboardPage } from "@/pages/DashboardPage";
import { PortfolioPage } from "@/pages/PortfolioPage";
import { MarketPage } from "@/pages/MarketPage";
import { RiskPage } from "@/pages/RiskPage";
import { ChatPage } from "@/pages/ChatPage";
import { LoginScreen } from "@/components/LoginScreen";
import {
  PageTransition,
  LoginExitOverlay,
  DashboardEnterFade,
  DASHBOARD_ENTER_DURATION_MS,
} from "@/components/PageTransition";
import { INTRO_TIMING } from "@/components/LoginScreen";
import { ThemeProvider } from "@/context/ThemeContext";
import { mockUser } from "@/data/mockData";
import type { ScreenId } from "@/types/finance";

// Faz 5'in (Dashboard'un giriş sonrası kart/grafik stagger'ı) görsel olarak
// bitmesi için gereken süre, artı LoginScreen→Dashboard crossfade süresi
// (INTRO_TIMING.loginHandoffMs) ve küçük bir tampon. Tek kaynak
// PageTransition.tsx'teki DASHBOARD_ENTER_DURATION_MS — burada hardcoded bir
// ms değeri tutulmuyor. Bu süre dolunca justLoggedIn sıfırlanır, yoksa
// Dashboard'a her geri dönüşte stagger tekrar oynardı.
const DASHBOARD_INTRO_RESET_MS = DASHBOARD_ENTER_DURATION_MS + INTRO_TIMING.loginHandoffMs + 200;

/**
 * Ekran kimliği ↔ URL yolu. Header ve DashboardPage hâlâ `ScreenId` ile
 * konuşuyor (bileşenlerin prop arayüzü değişmedi); yalnızca App bunu
 * react-router yoluna çeviriyor.
 */
const SCREEN_PATHS: Record<ScreenId, string> = {
  dashboard: "/dashboard",
  portfolio: "/portfolio",
  market: "/market",
  risk: "/risk",
  chat: "/chat",
};

const SCREEN_IDS = Object.keys(SCREEN_PATHS) as ScreenId[];

function screenFromPath(pathname: string): ScreenId {
  const match = SCREEN_IDS.find((id) => pathname.startsWith(SCREEN_PATHS[id]));
  return match ?? "dashboard";
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [justLoggedIn, setJustLoggedIn] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const screen = screenFromPath(location.pathname);

  useEffect(() => {
    if (!justLoggedIn) return;
    const t = window.setTimeout(() => setJustLoggedIn(false), DASHBOARD_INTRO_RESET_MS);
    return () => window.clearTimeout(t);
  }, [justLoggedIn]);

  const handleLogin = () => {
    setJustLoggedIn(true);
    setAuthenticated(true);
  };

  const handleNavigate = (next: ScreenId) => navigate(SCREEN_PATHS[next]);

  return (
    <ThemeProvider>
      {/* GİRİŞ NEDEN AYRI BİR ROUTE ("/login") DEĞİL:
          LoginScreen→Dashboard geçişi tasarlanmış bir crossfade
          (LoginExitOverlay + DashboardEnterFade, bkz. PageTransition.tsx);
          route değişimiyle kurulsaydı iki ağaç aynı anda mount kalamaz ve
          arada boş kare görünürdü. Ayrıca perde olarak durması sayesinde
          kullanıcı /risk adresini doğrudan açtığında giriş sonrası oraya
          düşer — /login'e yönlendirip hedefi kaybetmez.
          Faz 2'de `authenticated` state'inin yerini AuthContext alacak;
          bu yapı değişmeyecek. */}
      <AnimatePresence>
        {!authenticated && (
          <LoginExitOverlay key="login">
            <LoginScreen onSubmit={handleLogin} />
          </LoginExitOverlay>
        )}
      </AnimatePresence>

      {authenticated && (
        <DashboardEnterFade>
          <div className="min-h-screen bg-surface">
            {/* AnimatePresence mode="wait" sayfa geçişinde eski sayfayı tamamen
                unmount edip yenisini sonra mount ediyor — BackgroundLayer bu
                iki main içeriğinden ayrı, burada TEK örnek olarak render
                edilir ki sayfa değişse de katman hiç unmount olmasın. */}
            <BackgroundLayer variant={screen === "dashboard" ? "prominent" : "subtle"} />
            <Header user={mockUser} activeScreen={screen} onNavigate={handleNavigate} />

            <main className="relative z-[1] mx-auto max-w-[1440px] px-4 py-6 pb-24 sm:px-6 sm:py-9 md:px-10">
              <AnimatePresence mode="wait">
                <Routes location={location} key={location.pathname}>
                  <Route path="/" element={<Navigate to={SCREEN_PATHS.dashboard} replace />} />
                  <Route
                    path={SCREEN_PATHS.dashboard}
                    element={
                      <PageTransition dashboardEnter={justLoggedIn}>
                        <DashboardPage onNavigate={handleNavigate} introSequence={justLoggedIn} />
                      </PageTransition>
                    }
                  />
                  <Route
                    path={SCREEN_PATHS.portfolio}
                    element={
                      <PageTransition>
                        <PortfolioPage />
                      </PageTransition>
                    }
                  />
                  <Route
                    path={SCREEN_PATHS.market}
                    element={
                      <PageTransition>
                        <MarketPage />
                      </PageTransition>
                    }
                  />
                  <Route
                    path={SCREEN_PATHS.risk}
                    element={
                      <PageTransition>
                        <RiskPage />
                      </PageTransition>
                    }
                  />
                  <Route
                    path={SCREEN_PATHS.chat}
                    element={
                      <PageTransition>
                        <ChatPage />
                      </PageTransition>
                    }
                  />
                  {/* Tanınmayan adres sessizce dashboard'a düşer (SPA fallback
                      nginx tarafında zaten var, bkz. Dockerfile.prod). */}
                  <Route path="*" element={<Navigate to={SCREEN_PATHS.dashboard} replace />} />
                </Routes>
              </AnimatePresence>
            </main>

            {screen !== "chat" && <ChatWidget />}
          </div>
        </DashboardEnterFade>
      )}
    </ThemeProvider>
  );
}
