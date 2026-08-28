import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  fetchCurrentUser,
  login as loginRequest,
  register as registerRequest,
  type AuthUser,
  type RegisterRequest,
} from "@/api/auth";
import { isApiConfigured, setAccessToken, setUnauthorizedHandler } from "@/api/client";
import type { User } from "@/types/finance";

/**
 * Oturum durumu.
 *
 * TOKEN NEREDE DURUYOR: `localStorage`. Sayfa yenilendiğinde oturumun
 * sürmesi için bir yerde kalıcı olması gerekiyor ve seçenekler şunlardı:
 * bellek (yenilemede kaybolur — 8 saatlik demo token'ı için can sıkıcı),
 * `httpOnly` çerez (XSS'e karşı en güvenlisi ama sunucuda CSRF koruması,
 * SameSite ayarı ve çerez tabanlı bir akış gerektirir; bu sürümde yok) ya da
 * `localStorage`. Bilinen ödünü şudur: sayfada bir XSS açığı varsa token
 * okunabilir. Demo/POC kapsamı için kabul edildi, gerçek dağıtımda çerezli
 * akışa geçilmeli.
 */

const STORAGE_KEY = "vira_auth_token";

type AuthStatus = "checking" | "anonymous" | "authenticated";

interface AuthContextValue {
  status: AuthStatus;
  /**
   * Giriş ekranında gösterilecek bilgi notu (ör. oturum süresi doldu).
   * Kullanıcı sessizce dışarı atılmasın diye: 401 alındığında oturum
   * kapanıyor ama sebebi ekranda yazmıyordu.
   */
  notice: string | null;
  /** Giriş yapmış kullanıcının backend'den gelen kaydı. */
  account: AuthUser | null;
  /** Header'ın beklediği görünüm modeli (ad + baş harfler + rol). */
  user: User;
  /** Başarılıysa çözülür; başarısızsa kullanıcıya gösterilebilir bir hata fırlatır. */
  login: (nationalId: string, password: string) => Promise<void>;
  /**
   * Hesap açar ve DOĞRUDAN oturum açar.
   *
   * Kayıt yanıtı token taşıyor; ayrıca `login` çağırmak kullanıcıyı yeni
   * belirlediği şifreyi hemen yeniden yazmaya zorlardı.
   */
  register: (payload: RegisterRequest) => Promise<void>;
  /**
   * Kullanıcı kaydını sunucudan tazeler.
   *
   * Anket tamamlandığında gerekiyor: `risk_survey_score` sunucuda değişiyor
   * ama oturumdaki kopya eski kalıyor ve anket ekranı kalkmıyordu. Sayfayı
   * yeniden yüklemek yerine tek bir istek.
   */
  refreshAccount: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Gizli sekme ya da site verisi kapalı tarayıcı: erişimin kendisi
    // fırlatabiliyor. Oturum o sekmede sürmez, ama uygulama çökmemeli.
    return null;
  }
}

function writeStoredToken(token: string | null): void {
  try {
    if (token === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* yukarıdaki gerekçe */
  }
}

/**
 * "Ahmet Yılmaz" → "AY". Türkçe adlarda `toLocaleUpperCase("tr")` şart:
 * varsayılan büyütme "i" harfini "I" yapar, doğrusu "İ".
 */
function initialsOf(fullName: string): string {
  const parcalar = fullName.trim().split(/\s+/).filter(Boolean);
  if (parcalar.length === 0) return "?";
  const ilk = parcalar[0][0];
  const son = parcalar.length > 1 ? parcalar[parcalar.length - 1][0] : "";
  return (ilk + son).toLocaleUpperCase("tr-TR");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<AuthUser | null>(null);
  // API adresi tanımlı değilse doğrulanacak bir şey yok; "checking" durumunda
  // sonsuza kadar beklemek yerine doğrudan anonim başlıyoruz.
  const [status, setStatus] = useState<AuthStatus>(isApiConfigured ? "checking" : "anonymous");
  const [notice, setNotice] = useState<string | null>(null);
  /**
   * `sebep` yalnızca oturum KENDİLİĞİNDEN düştüğünde veriliyor (401). Kullanıcı
   * "Çıkış Yap" dediğinde not gösterilmiyor — zaten kendi yaptığı bir şey.
   */
  const logout = useCallback((sebep?: "expired") => {
    writeStoredToken(null);
    setAccessToken(null);
    setAccount(null);
    setStatus("anonymous");
    setNotice(sebep === "expired" ? "Oturumunuz sona erdi, lütfen tekrar giriş yapın." : null);
  }, []);

  // Token süresi dolduğunda (herhangi bir istekte 401) oturumu kapat.
  useEffect(() => {
    setUnauthorizedHandler(() => logout("expired"));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Sayfa yenilendiğinde: saklanan token'ı sunucuya doğrulat. Token'ın
  // içeriğini istemcide çözüp "süresi dolmuş mu" diye BAKMIYORUZ — istemcinin
  // saati yanlış olabilir ve kullanıcı silinmiş de olabilir; tek doğru cevap
  // sunucudan gelir.
  //
  // BURADA "YALNIZCA BİR KEZ ÇALIŞSIN" BAYRAĞI KULLANILMAZ. Bir `useRef`
  // bayrağıyla effect'in ikinci çalışmasını engellemek, React 18
  // StrictMode'da kalıcı BEYAZ EKRAN üretiyordu ve canlıda ölçüldü:
  //
  //   1. İlk takılışta bayrak set edilir, istek başlar, temizlik döndürülür.
  //   2. StrictMode bileşeni söker → temizlik çalışır → `iptal = true`.
  //   3. İkinci takılışta bayrak yüzünden effect HİÇ çalışmaz.
  //   4. 1. adımdaki isteğin cevabı gelir ama `iptal` true olduğu için
  //      durum güncellenmez → `status` sonsuza dek "checking" kalır → App
  //      o durumda boş bir div render eder.
  //
  // Token geçerli olsa bile oluyordu: hata token'da değil, akıştaydı.
  // Doğrusu, React'in belgelediği desen — bayrak yok, yalnızca iptal
  // bayrağı. StrictMode'da istek iki kez gider; `/api/auth/me` salt okuma
  // olduğu için bunun bir maliyeti yok, kalıcı beyaz ekranın ise var.
  useEffect(() => {
    const token = readStoredToken();
    if (!token || !isApiConfigured) {
      setStatus("anonymous");
      return;
    }

    setAccessToken(token);
    let iptal = false;
    fetchCurrentUser()
      .then((kullanici) => {
        if (iptal) return;
        setAccount(kullanici);
        setStatus("authenticated");
      })
      .catch(() => {
        if (iptal) return;
        // Saklanan token artık geçerli değil — kullanıcı için bu da "oturum
        // sona erdi" demek.
        logout("expired");
      });

    return () => {
      iptal = true;
    };
  }, [logout]);

  const login = useCallback(async (nationalId: string, password: string) => {
    const yanit = await loginRequest(nationalId, password);
    setNotice(null);
    writeStoredToken(yanit.access_token);
    setAccessToken(yanit.access_token);
    setAccount(yanit.user);
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (payload: RegisterRequest) => {
    const yanit = await registerRequest(payload);
    setNotice(null);
    writeStoredToken(yanit.access_token);
    setAccessToken(yanit.access_token);
    setAccount(yanit.user);
    setStatus("authenticated");
  }, []);

  const refreshAccount = useCallback(async () => {
    // Hata YUTULUYOR: bu bir tazeleme, kritik yol değil. Başarısız olursa
    // eldeki (eski ama geçerli) kayıtla devam edilir; token gerçekten
    // düşmüşse zaten global 401 işleyicisi oturumu kapatır.
    try {
      setAccount(await fetchCurrentUser());
    } catch {
      /* yukarıdaki gerekçe */
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      notice,
      account,
      user: {
        name: account?.full_name ?? "",
        initials: account ? initialsOf(account.full_name) : "",
        // Rol alanı sistemde yok; hedef kullanıcı tanımı sabit
        // (CLAUDE.md A3: kendi portföyünü yöneten bireysel yatırımcı).
        role: "Bireysel Yatırımcı",
      },
      login,
      register,
      refreshAccount,
      logout,
    }),
    [status, notice, account, login, register, refreshAccount, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth, AuthProvider içinde çağrılmalı.");
  }
  return context;
}

/**
 * Giriş yapmış kullanıcının kimliği. Veri çeken hook'lar bunu uçlara
 * geçirir — `user_id` artık hiçbir yerde elle girilmiyor.
 */
export function useCurrentUserId(): string | null {
  return useAuth().account?.id ?? null;
}
