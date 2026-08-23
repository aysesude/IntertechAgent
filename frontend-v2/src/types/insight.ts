export type InsightSeverity = "uyari" | "olumlu" | "bilgi";
export type InsightAgent = "portfoy" | "risk" | "piyasa";

export interface InsightEvidence {
  label: string;
  value: string;
}

export interface Insight {
  id: string;
  severity: InsightSeverity;
  agent: InsightAgent;
  title: string; // kısa başlık
  body: string; // ne oldu + sana etkisi, 1-2 cümle
  amountTRY?: number; // varsa parasal etki
  evidence: InsightEvidence[]; // 'neden?' altında gösterilecek dayanak
}
