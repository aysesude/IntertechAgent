import { apiGet, apiPost } from "./client";

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
