import { apiGet, apiPost, apiPostNoContent } from "./client";

/**
 * Giriş uçları. Şekiller backend/app/schemas/auth.py ile birebir eşleşir.
 *
 * Arayüzdeki "T.C. Kimlik Numarası" alanı burada `national_id`'ye eşlenir —
 * kod İngilizce, kullanıcıya görünen metin Türkçe (CLAUDE.md).
 */

export interface AuthUser {
  id: string;
  full_name: string;
  risk_profile: "conservative" | "balanced" | "growth" | "aggressive";
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export function login(nationalId: string, password: string): Promise<TokenResponse> {
  return apiPost<TokenResponse>(
    "/api/auth/login",
    { national_id: nationalId, password },
    // Yanlış şifrede gelen 401 "oturum düştü" değildir; global oturum
    // kapatma akışını tetiklememeli.
    { skipUnauthorizedHandler: true },
  );
}

/** Elimizdeki token hâlâ geçerli mi ve kime ait? Sayfa yenilendiğinde çağrılır. */
export function fetchCurrentUser(): Promise<AuthUser> {
  return apiGet<AuthUser>("/api/auth/me", { skipUnauthorizedHandler: true });
}

// ---------------------------------------------------------------------------
// Şifre yenileme (DEMO akışı)
// ---------------------------------------------------------------------------
//
// TEMSİLİ olan: e-posta gönderilmez, kod sunucuda üretilip saklanmaz —
// yapılandırmadaki sabit kod kabul edilir.
// GERÇEK olan: şifre veritabanında güncellenir; kullanıcı bundan sonra yeni
// şifresiyle giriş yapar.

export interface PasswordResetInfo {
  /** Kod alanının kaç haneli olacağı — arayüz sabit yazmasın diye sunucudan. */
  code_length: number;
  /** Geri sayımın süresi (saniye). */
  expires_in_seconds: number;
}

export function requestPasswordReset(nationalId: string): Promise<PasswordResetInfo> {
  return apiPost<PasswordResetInfo>(
    "/api/auth/password-reset/request",
    { national_id: nationalId },
    // Bu akış giriş yapmamış kullanıcı içindir; buradan dönen bir hata
    // "oturum düştü" demek değildir.
    { skipUnauthorizedHandler: true },
  );
}

export function completePasswordReset(
  nationalId: string,
  code: string,
  newPassword: string,
): Promise<void> {
  // Sunucu 204 (gövdesiz) dönüyor; `apiPost` JSON çözmeye çalışırsa patlar.
  return apiPostNoContent(
    "/api/auth/password-reset/complete",
    { national_id: nationalId, code, new_password: newPassword },
    { skipUnauthorizedHandler: true },
  );
}
