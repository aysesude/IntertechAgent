import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * AuthProvider testleri.
 *
 * Bu dosyanın var olma sebebi somut: test ortamında giriş yaptıktan sonra
 * sayfayı her yenilemede KALICI BEYAZ EKRAN geliyordu ve hata ancak
 * tarayıcıda fark edildi. Sebep, oturum geri yükleme effect'indeki bir
 * `useRef` bayrağının React 18 StrictMode'un ikinci çalıştırmasını
 * engellemesiydi: durumu güncelleyen tek yol kapanıyor, `status` sonsuza dek
 * "checking" kalıyordu.
 *
 * Bu yüzden testlerin bir kısmı bileşeni BİLEREK `<StrictMode>` içinde
 * render ediyor — uygulamanın kendisi de öyle çalışıyor (src/main.tsx) ve
 * hata yalnızca o koşulda ortaya çıkıyor.
 */

// API katmanı taklit ediliyor: bu testler ağa çıkmaz, AuthProvider'ın
// AKIŞINI sınar. Uçların kendisi backend tarafında test ediliyor
// (tests/test_auth_api.py).
const fetchCurrentUser = vi.fn();
const loginRequest = vi.fn();
const setAccessToken = vi.fn();
const setUnauthorizedHandler = vi.fn();

vi.mock("@/api/auth", () => ({
  fetchCurrentUser: (...args: unknown[]) => fetchCurrentUser(...args),
  login: (...args: unknown[]) => loginRequest(...args),
}));

vi.mock("@/api/client", () => ({
  isApiConfigured: true,
  setAccessToken: (...args: unknown[]) => setAccessToken(...args),
  setUnauthorizedHandler: (...args: unknown[]) => setUnauthorizedHandler(...args),
}));

const { AuthProvider, useAuth } = await import("./AuthContext");

const STORAGE_KEY = "vira_auth_token";

const HESAP = {
  id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  full_name: "Ahter İnönü",
  risk_profile: "conservative" as const,
};

/** Context'in dışarıya verdiği her şeyi ekrana basan yardımcı bileşen. */
function Gosterge() {
  const { status, user, account, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="name">{user.name}</span>
      <span data-testid="initials">{user.initials}</span>
      <span data-testid="account-id">{account?.id ?? "-"}</span>
      <span data-testid="notice">{useAuth().notice ?? "-"}</span>
      <button onClick={() => void login("36542351188", "460213").catch(() => {})}>giris</button>
      <button onClick={logout}>cikis</button>
    </div>
  );
}

function renderProvider({ strict }: { strict: boolean }) {
  const agac = (
    <AuthProvider>
      <Gosterge />
    </AuthProvider>
  );
  return render(strict ? <StrictMode>{agac}</StrictMode> : agac);
}

beforeEach(() => {
  window.localStorage.clear();
  fetchCurrentUser.mockReset();
  loginRequest.mockReset();
  setAccessToken.mockReset();
  setUnauthorizedHandler.mockReset();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("oturumun geri yüklenmesi", () => {
  it("saklanmış token yoksa doğrudan anonim olur ve sunucuya sormaz", async () => {
    renderProvider({ strict: false });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(fetchCurrentUser).not.toHaveBeenCalled();
  });

  it("geçerli token'la oturumu geri yükler", async () => {
    window.localStorage.setItem(STORAGE_KEY, "saklanan-token");
    fetchCurrentUser.mockResolvedValue(HESAP);

    renderProvider({ strict: false });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("account-id")).toHaveTextContent(HESAP.id);
    // Token, istek atılmadan ÖNCE istemci katmanına verilmeli; yoksa
    // /api/auth/me isteği Authorization başlığı taşımaz.
    expect(setAccessToken).toHaveBeenCalledWith("saklanan-token");
  });

  it("token geçersizse oturumu kapatır ve depodan siler", async () => {
    window.localStorage.setItem(STORAGE_KEY, "suresi-dolmus");
    fetchCurrentUser.mockRejectedValue(new Error("401"));

    renderProvider({ strict: false });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  // --- Beyaz ekran hatasının bekçisi ---------------------------------------

  it("StrictMode'da geçerli token'la ASLA 'checking' durumunda takılmaz", async () => {
    // GERİLEME TESTİ. React 18 StrictMode bileşeni bir kez söküp yeniden
    // takıyor. Effect'in ikinci çalışmasını bir bayrakla engellersek, ilk
    // çalışmanın temizliği "iptal" işaretini koyduğu için gelen cevap
    // yok sayılır ve durum hiç güncellenmez. Uygulama o durumda boş bir div
    // render ettiği için sonuç kalıcı beyaz ekrandır.
    window.localStorage.setItem(STORAGE_KEY, "gecerli-token");
    fetchCurrentUser.mockResolvedValue(HESAP);

    renderProvider({ strict: true });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("name")).toHaveTextContent("Ahter İnönü");
  });

  it("StrictMode'da geçersiz token'la da 'checking' durumunda takılmaz", async () => {
    // Aynı hatanın hata dalı: cevap reddedilirse de durum güncellenmiyordu.
    window.localStorage.setItem(STORAGE_KEY, "suresi-dolmus");
    fetchCurrentUser.mockRejectedValue(new Error("401"));

    renderProvider({ strict: true });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });
});

describe("giriş ve çıkış", () => {
  it("başarılı girişte token saklanır ve kullanıcı yerleşir", async () => {
    loginRequest.mockResolvedValue({
      access_token: "yeni-token",
      token_type: "bearer",
      expires_in: 28800,
      user: HESAP,
    });

    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    await act(async () => {
      screen.getByText("giris").click();
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("yeni-token");
    expect(setAccessToken).toHaveBeenCalledWith("yeni-token");
  });

  it("başarısız giriş oturumu açmaz ve token saklamaz", async () => {
    loginRequest.mockRejectedValue(new Error("T.C. kimlik numarası veya şifre hatalı."));

    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    await act(async () => {
      screen.getByText("giris").click();
    });

    expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("çıkış token'ı siler ve istemci katmanını temizler", async () => {
    window.localStorage.setItem(STORAGE_KEY, "gecerli-token");
    fetchCurrentUser.mockResolvedValue(HESAP);

    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await act(async () => {
      screen.getByText("cikis").click();
    });

    expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    // Sonraki isteklere eski token'ın yapışmaması için.
    expect(setAccessToken).toHaveBeenLastCalledWith(null);
  });

  it("401 gelirse oturumu kapatacak bir işleyici kaydeder", async () => {
    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    // İstemci katmanı, herhangi bir istekte 401 görürse bunu çağırıyor.
    expect(setUnauthorizedHandler).toHaveBeenCalled();
    // `findLast` ES2023; tsconfig hedefi ES2020 olduğu için ters çevirip
    // `find` kullanıyoruz — davranış aynı, ek kütüphane gerekmiyor.
    const isleyici = [...setUnauthorizedHandler.mock.calls]
      .reverse()
      .map((cagri) => cagri[0] as unknown)
      .find((fn): fn is () => void => typeof fn === "function");
    expect(isleyici).toBeTypeOf("function");

    window.localStorage.setItem(STORAGE_KEY, "artik-gecersiz");
    await act(async () => {
      isleyici!();
    });
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe("baş harfler", () => {
  it.each([
    ["Ahter İnönü", "Aİ"],
    ["ilker yılmaz", "İY"],
    ["Aliihsan Tunahan Duran Karadeniz", "AK"],
    ["Tek", "T"],
  ])("%s -> %s", async (adSoyad, beklenen) => {
    // Türkçe büyütme kuralı: "i" harfinin büyüğü "I" değil "İ".
    // Varsayılan toUpperCase() kullanılsaydı "ilker" -> "IY" çıkardı.
    window.localStorage.setItem(STORAGE_KEY, "gecerli-token");
    fetchCurrentUser.mockResolvedValue({ ...HESAP, full_name: adSoyad });

    renderProvider({ strict: false });

    await waitFor(() => expect(screen.getByTestId("initials")).toHaveTextContent(beklenen));
  });
});

describe("oturum sona erdi bildirimi", () => {
  it("401 işleyicisi tetiklenince kullanıcıya SEBEBİ söylenir", async () => {
    // Eskiden oturum sessizce kapanıyordu: kullanıcı giriş ekranına
    // düşüyor ama neden atıldığını göremiyordu.
    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    const isleyici = [...setUnauthorizedHandler.mock.calls]
      .reverse()
      .map((cagri) => cagri[0] as unknown)
      .find((fn): fn is () => void => typeof fn === "function");

    await act(async () => {
      isleyici!();
    });
    expect(screen.getByTestId("notice")).toHaveTextContent("Oturumunuz sona erdi");
  });

  it("saklanan token geçersizse de aynı bildirim gösterilir", async () => {
    window.localStorage.setItem(STORAGE_KEY, "suresi-dolmus");
    fetchCurrentUser.mockRejectedValue(new Error("401"));

    renderProvider({ strict: false });

    await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent("Oturumunuz sona erdi"));
  });

  it("kullanıcı KENDİ çıkış yaptığında bildirim gösterilmez", async () => {
    // Kendi yaptığı bir eylemi ona açıklamak gereksiz gürültü.
    window.localStorage.setItem(STORAGE_KEY, "gecerli-token");
    fetchCurrentUser.mockResolvedValue(HESAP);

    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await act(async () => {
      screen.getByText("cikis").click();
    });
    expect(screen.getByTestId("notice")).toHaveTextContent("-");
  });

  it("başarılı giriş bildirimi temizler", async () => {
    loginRequest.mockResolvedValue({
      access_token: "yeni-token",
      token_type: "bearer",
      expires_in: 28800,
      user: HESAP,
    });
    window.localStorage.setItem(STORAGE_KEY, "suresi-dolmus");
    fetchCurrentUser.mockRejectedValue(new Error("401"));

    renderProvider({ strict: false });
    await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent("Oturumunuz sona erdi"));

    await act(async () => {
      screen.getByText("giris").click();
    });
    await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent("-"));
  });
});
