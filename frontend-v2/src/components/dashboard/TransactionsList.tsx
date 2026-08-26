import type { Transaction } from "@/types/finance";
import { Card } from "@/components/common/Card";
import { ArrowUpIcon, ArrowDownIcon, MinusIcon } from "@/components/icons";

interface TransactionsListProps {
  transactions: Transaction[];
}

const DIRECTION_STYLES: Record<Transaction["direction"], { bg: string; fg: string; Icon: typeof ArrowUpIcon; amount: string }> = {
  in: { bg: "bg-brand-tint", fg: "text-brand", Icon: ArrowUpIcon, amount: "text-brand" },
  out: { bg: "bg-danger-tint", fg: "text-danger", Icon: ArrowDownIcon, amount: "text-danger" },
  neutral: { bg: "bg-line2", fg: "text-ink-muted", Icon: MinusIcon, amount: "text-ink-soft" },
};

export function TransactionsList({ transactions }: TransactionsListProps) {
  return (
    <Card className="p-6">
      <h2 className="font-display m-0 mb-[18px] text-[17px] font-semibold">Son İşlemler</h2>
      <div className="flex flex-col">
        {transactions.map((tx, i) => {
          const style = DIRECTION_STYLES[tx.direction];
          const Icon = style.Icon;
          return (
            <div
              key={tx.id}
              className={`flex items-center gap-3.5 py-3.5 ${i < transactions.length - 1 ? "border-b border-line2 dark:border-transparent" : ""}`}
            >
              <span className={`grid h-9 w-9 place-items-center rounded-[9px] ${style.bg} ${style.fg}`}>
                <Icon size={16} />
              </span>
              <div className="flex-1">
                <div className="text-sm font-semibold">{tx.title}</div>
                <div className="text-xs text-ink-faint">
                  {tx.date} · {tx.detail}
                </div>
              </div>
              <div className={`text-sm font-semibold ${style.amount}`}>{tx.formattedAmount}</div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
