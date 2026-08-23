import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/context/ThemeContext", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

const { PasswordResetCard } = await import("./PasswordResetCard");

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

/** 1. adımı geçip kod ekranına gelir. */
function kimlikAdiminiGec() {
  yaz(/T\.C\. Kimlik/i, GECERLI_TCKN);
  fireEvent.click(screen.getByRole("button", { name: /doğrulama kodu gönder/i }));
}

/** 2. adımı geçip yeni şifre ekranına gelir. */
function kodAdiminiGec() {
  yaz(/Doğrulama Kodu/i, "123456");
  fireEvent.click(screen.getByRole("button", { name: /^doğrula$/i }));
}

describe("1. adım — kimlik", () => {
  it("geçersiz T.C. kimlik numarasıyla ilerlemez", () => {
    kur();
    // Sağlaması tutmayan numara: 11 hane ama son hane bozuk.
    yaz(/T\.C\. Kimlik/i, "55868501481");
    fireEvent.click(screen.getByRole("button", { name: /doğrulama kodu gönder/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("Geçerli bir T.C. kimlik numarası girin.");
    expect(screen.queryByLabelText(/Doğrulama Kodu/i)).not.toBeInTheDocument();
  });

  it("geçerli numarayla kod adımına geçer", () => {
    kur();
    kimlikAdiminiGec();

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
  it("eksik kodla ilerlemez", () => {
    kur();
    kimlikAdiminiGec();

    yaz(/Doğrulama Kodu/i, "123");
    fireEvent.click(screen.getByRole("button", { name: /^doğrula$/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("6 haneli olmalı");
    expect(screen.queryByLabelText(/Yeni Şifreniz$/i)).not.toBeInTheDocument();
  });

  it("sayaç dolmadan 'Tekrar gönder' tıklanamaz", () => {
    // Aksi halde kullanıcı arka arkaya kod isteyebilir; gerçek bir akışta
    // bu sunucuya yük ve kötüye kullanım kapısı olurdu.
    kur();
    kimlikAdiminiGec();

    expect(screen.getByRole("button", { name: /tekrar gönder/i })).toBeDisabled();
    expect(screen.getByText(/Kalan süre/i)).toBeInTheDocument();
  });

  it("6 haneli kodla şifre adımına geçer", () => {
    kur();
    kimlikAdiminiGec();
    kodAdiminiGec();

    expect(screen.getByLabelText(/Yeni Şifreniz$/i)).toBeInTheDocument();
  });
});

describe("3. adım — yeni şifre", () => {
  it("şifreler eşleşmiyorsa tamamlanmaz", () => {
    kur();
    kimlikAdiminiGec();
    kodAdiminiGec();

    yaz(/Yeni Şifreniz$/i, "123456");
    yaz(/Yeni Şifreniz \(Tekrar\)/i, "654321");
    fireEvent.click(screen.getByRole("button", { name: /şifreyi güncelle/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("Şifreler eşleşmiyor.");
  });

  it("eksik şifreyle tamamlanmaz", () => {
    kur();
    kimlikAdiminiGec();
    kodAdiminiGec();

    yaz(/Yeni Şifreniz$/i, "123");
    yaz(/Yeni Şifreniz \(Tekrar\)/i, "123");
    fireEvent.click(screen.getByRole("button", { name: /şifreyi güncelle/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("6 haneli olmalı");
  });

  it("eşleşen şifreyle başarı ekranına ulaşır", () => {
    kur();
    kimlikAdiminiGec();
    kodAdiminiGec();

    yaz(/Yeni Şifreniz$/i, "123456");
    yaz(/Yeni Şifreniz \(Tekrar\)/i, "123456");
    fireEvent.click(screen.getByRole("button", { name: /şifreyi güncelle/i }));

    expect(screen.getByText(/Şifren güncellendi/i)).toBeInTheDocument();
  });
});

describe("girişe dönüş", () => {
  it("her adımdan giriş ekranına dönülebilir", () => {
    const { onBack } = kur();
    fireEvent.click(screen.getByRole("button", { name: /giriş ekranına dön/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("başarı ekranından da dönülür", () => {
    const { onBack } = kur();
    kimlikAdiminiGec();
    kodAdiminiGec();
    yaz(/Yeni Şifreniz$/i, "123456");
    yaz(/Yeni Şifreniz \(Tekrar\)/i, "123456");
    fireEvent.click(screen.getByRole("button", { name: /şifreyi güncelle/i }));

    fireEvent.click(screen.getByRole("button", { name: /giriş ekranına dön/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
