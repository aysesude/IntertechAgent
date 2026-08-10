export type AssetClass = "stock" | "gold" | "currency" | "bond";

export interface GainLoss {
  amount: number;
  percent: number;
}

export interface AllocationItem {
  asset_class: AssetClass;
  value: number;
  percent: number;
}

export interface PortfolioSummary {
  user_id: string;
  as_of: string;
  total_value: number;
  total_cost_basis: number;
  total_gain_loss: GainLoss;
  allocation: AllocationItem[];
  holdings_count: number;
}
