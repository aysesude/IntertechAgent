export function formatTRY(value: number): string {
  return "₺" + Math.round(value).toLocaleString("tr-TR");
}

export function formatTRYCompact(value: number): string {
  return "₺" + (value / 1_000_000).toFixed(2).replace(".", ",") + "M";
}

export function formatPct(value: number, digits = 2): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const abs = Math.abs(value).toFixed(digits).replace(".", ",");
  return `${sign}${abs}%`;
}

export function formatSignedTRY(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${formatTRY(Math.abs(value))}`;
}

/**
 * Para birimine göre 2 ondalıklı biçim. `null` = BİRİMSİZ (endeks puanı,
 * parite) — başına simge konmaz, çünkü "₺11.284" BIST 100 için olmayan bir
 * büyüklük iddiasıdır. Bilinmeyen bir para birimi kodu, uydurma bir simge
 * yerine kodun kendisiyle yazılır ("88,04 GBP").
 */
export function formatMoney2(value: number, currency: string | null): string {
  if (currency === null) return formatNumberTR(value, 2);
  if (currency === "TRY") return formatTRY2(value);
  const sayi = formatNumberTR(value, 2);
  if (currency === "USD") return `$${sayi}`;
  if (currency === "EUR") return `€${sayi}`;
  return `${sayi} ${currency}`;
}

/** Türkçe binlik ("."), ondalık (",") ayıraçlı düz sayı — para birimi yok. */
export function formatNumberTR(value: number, digits = 0): string {
  return value.toLocaleString("tr-TR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** formatTRY'nin 2 ondalıklı hali — Getiri Detayları panelindeki para değerleri için. */
export function formatTRY2(value: number): string {
  return "₺" + value.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatSignedTRY2(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${formatTRY2(Math.abs(value))}`;
}

/** ISO tarihten "GG/AA/YYYY" — toLocaleDateString('tr-TR') nokta kullanıyor, burada bilerek slash. */
export function formatDateDMY(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

/**
 * Bir miktarı enstrümanın birim etiketine göre biçimlendirir — HoldingsTable'ın
 * "Adet" sütunu ve Getiri Detayları panelinin özet/parti satırları AYNI
 * kaynaktan (bu fonksiyon) okur, ikisi arasında biçim tutarsızlığı olmaz.
 */
export function formatQuantityByUnit(quantity: number, unitLabel: string): string {
  const n = formatNumberTR(quantity, 0);
  switch (unitLabel) {
    case "adet":
      return n;
    case "gr":
      return `${n} gr`;
    case "$":
      return `$${n}`;
    case "€":
      return `€${n}`;
    case "₺":
      return `₺${n}`;
    default:
      return `${n} ${unitLabel}`;
  }
}
