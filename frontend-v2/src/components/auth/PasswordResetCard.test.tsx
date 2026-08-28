import { act } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/context/ThemeContext", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

const requestPasswordReset = vi.fn();
const completePasswordReset = vi.fn();
vi.mock("@/api/auth", () => ({
  requestPasswordReset: (...a: unknown[]) => requestPasswordReset(...a),
  completePasswordReset: (...a: unknown[]) => completePasswordReset(...a),
}));

const { PasswordResetCard } = await import("./PasswordResetCard");

beforeEach(() => {
  // Kod uzunluğu ve süre SUNUCUDAN geliyor; arayüz bunları sabit yazmıyor.
  requestPasswordReset.mockReset().mockResolvedValue({ code_length: 6, expires_in_seconds: 180 });
  completePasswordReset.mockReset().mockResolvedValue(undefined);
});

/**
 * Şifre yenileme akışı testleri.
 *
 * AKIŞ TEMSİLİDİR — sunucu tarafı yok, hiçbir şifre değişmiyor (bkz.
 * PasswordResetCard docstring). Bu testler o yüzden "şifre gerçekten
 * değişti mi"yi değil, ADIMLARIN ve DOĞRULAMALARIN doğru çalıştığını
 * sınıyor: kullanıcı geçersiz bir kimlikle ilerleyememeli, eşleşmeyen
 * şifrelerle bitirememeli, her adımda geri dönebilmeli.
 */

const GECERLI_TCKN = "55868501480"; // seed'in ürettiği gerçek numara

function yaz(etiket: RegExp, deger: string) {
  fireEvent.change(screen.getByLabelText(etiket), { target: { value: deger } });
}

function kur() {
  const onBack = vi.fn();
  render(<PasswordResetCard onBack={onBack} />);
  return { onBack };
}

/** 1. adımı geçip kod ekranına gelir (kod isteği sunucuya gidiyor). */
async function kimlikAdiminiGec() {
  yaz(/T\.C\. Kimlik/i, GECERLI_TCKN);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /doğrulama kodu gönder/i }));
  });
}

/** 2. adımı geçip yeni şifre ekranına gelir (kodun doğruluğu sunucuda sınanır). */
function kodAdiminiGec() {
  yaz(/Doğrulama Kodu/i, "123456");
  fireEvent.click(screen.getByRole("button", { name: /^doğrula$/i }));
}

/** 3. adımı doldurup gönderir. */
async function sifreyiGonder(sifre = "778899", tekrar = "778899") {
  yaz(/Yeni Şifreniz$/i, sifre);
  yaz(/Yeni Şifreniz \(Tekrar\)/i, tekrar);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /şifreyi güncelle/i }));
  });
}

describe("1. adım — kimlik", () => {
  it("eksik haneli T.C. kimlik numarasıyla ilerlemez", async () => {
    kur();
    // Sağlama kontrolü kaldırıldı (bkz. utils/tckn.ts): artık yalnızca
    // BİÇİM bağlayıcı. 10 hane, dolayısıyla reddedilmeli.
    yaz(/T\.C\. Kimlik/i, "5586850148");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /doğrulama kodu gönder/i }));
    });

    expect(screen.getByRole("alert")).toHaveTextContent("T.C. kimlik numarası 11 haneli olmalı.");
    expect(screen.queryByLabelText(/Doğrulama Kodu/i)).not.toBeInTheDocument();
    // Geçersiz numarada sunucuya HİÇ gidilmemeli.
    expect(requestPasswordReset).not.toHaveBeenCalled();
  });

  it("geçerli numarayla kod adımına geçer", async () => {
    kur();
    await kimlikAdiminiGec();

    expect(screen.getByLabelText(/Doğrulama Kodu/i)).toBeInTheDocument();
    // Kodun kaç haneli olduğu ve süresi kullanıcıya söylenmeli.
    expect(screen.getByText(/6 haneli bir doğrulama kodu gönderdik/i)).toBeInTheDocument();
  });

  it("harf girilemez", () => {
    kur();
    yaz(/T\.C\. Kimlik/i, "abc55868501480xyz");
    expect(screen.getByLabelText(/T\.C\. Kimlik/i)).toHaveValue("55868501480");
  });
});

describe("2. adım — doğrulama kodu", () => {
  it("eksik kodla ilerlemez", async () => {
    kur();
    await kimlikAdiminiGec();

    yaz(/Doğrulama Kodu/i, "123");
    fireEvent.click(screen.getByRole("button", { name: /^doğrula$/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("6 haneli olmalı");
    expect(screen.queryByLabelText(/Yeni Şifreniz$/i)).not.toBeInTheDocument();
  });

  it("sayaç dolmadan 'Tekrar gönder' tıklanamaz", async () => {
    // Aksi halde kullanıcı arka arkaya kod isteyebilir; gerçek bir akışta
    // bu sunucuya yük ve kötüye kullanım kapısı olurdu.
    kur();
    await kimlikAdiminiGec();

    expect(screen.getByRole("button", { name: /tekrar gönder/i })).toBeDisabled();
    expect(screen.getByText(/Kalan süre/i)).toBeInTheDocument();
  });

  it("6 haneli kodla şifre adımına geçer", async () => {
    kur();
    await kimlikAdiminiGec();
    kodAdiminiGec();

    expect(screen.getByLabelText(/Yeni Şifreniz$/i)).toBeInTheDocument();
  });
});

describe("3. adım — yeni şifre", () => {
  it("şifreler eşleşmiyorsa SUNUCUYA GİTMEZ", async () => {
    kur();
    await kimlikAdiminiGec();
    kodAdiminiGec();
    await sifreyiGonder("123456", "654321");

    expect(screen.getByRole("alert")).toHaveTextContent("Şifreler eşleşmiyor.");
    expect(completePasswordReset).not.toHaveBeenCalled();
  });

  it("eksik şifreyle tamamlanmaz", async () => {
    kur();
    await kimlikAdiminiGec();
    kodAdiminiGec();
    await sifreyiGonder("123", "123");

    expect(screen.getByRole("alert")).toHaveTextContent("6 haneli olmalı");
    expect(completePasswordReset).not.toHaveBeenCalled();
  });

  it("eşleşen şifreyle sunucuya gider ve başarı ekranına ulaşır", async () => {
    kur();
    await kimlikAdiminiGec();
    kodAdiminiGec();
    await sifreyiGonder();

    expect(completePasswordReset).toHaveBeenCalledWith(GECERLI_TCKN, "123456", "778899");
    expect(screen.getByText(/Şifren güncellendi/i)).toBeInTheDocument();
  });

  it("sunucu kodu reddederse KOD adımına geri döner", async () => {
    // Kodun doğruluğu ancak bu adımda anlaşılıyor; kullanıcı şifre alanında
    // sıkışıp kalmamalı, kodu yeniden girebilmeli.
    completePasswordReset.mockRejectedValue(
      new Error("T.C. kimlik numarası veya doğrulama kodu hatalı."),
    );
    kur();
    await kimlikAdiminiGec();
    kodAdiminiGec();
    await sifreyiGonder();

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("doğrulama kodu hatalı"),
    );
    expect(screen.getByLabelText(/Doğrulama Kodu/i)).toHaveValue("");
  });
});

describe("girişe dönüş", () => {
  it("her adımdan giriş ekranına dönülebilir", () => {
    const { onBack } = kur();
    fireEvent.click(screen.getByRole("button", { name: /giriş ekranına dön/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("başarı ekranından da dönülür", async () => {
    const { onBack } = kur();
    await kimlikAdiminiGec();
    kodAdiminiGec();
    await sifreyiGonder();

    fireEvent.click(screen.getByRole("button", { name: /giriş ekranına dön/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
