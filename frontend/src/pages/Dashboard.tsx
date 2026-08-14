import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { fetchPortfolioSummary } from "../api/portfolio";
import ChatBox from "../components/ChatBox";
import type { AssetClass } from "../types/portfolio";

const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  stock: "Hisse",
  precious_metal: "Kıymetli Maden",
  currency: "Döviz",
  bond: "Tahvil",
  cash: "Nakit",
};

const ASSET_CLASS_COLORS: Record<AssetClass, string> = {
  stock: "#2563eb",
  precious_metal: "#eab308",
  currency: "#16a34a",
  bond: "#7c3aed",
  cash: "#64748b",
};

const USER_ID_STORAGE_KEY = "finans_user_id";

function formatCurrency(value: number): string {
  return `${value.toLocaleString("tr-TR", { maximumFractionDigits: 2 })} TL`;
}

function Dashboard(): JSX.Element {
  const [userId, setUserId] = useState<string>(() => localStorage.getItem(USER_ID_STORAGE_KEY) ?? "");
  const [userIdInput, setUserIdInput] = useState(userId);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["portfolio", userId],
    queryFn: () => fetchPortfolioSummary(userId),
    enabled: userId.length > 0,
    retry: false,
  });

  function handleUserIdSubmit(e: React.FormEvent): void {
    e.preventDefault();
    localStorage.setItem(USER_ID_STORAGE_KEY, userIdInput);
    setUserId(userIdInput);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      <form onSubmit={handleUserIdSubmit} className="flex items-end gap-2">
        <div>
          <label className="mb-1 block text-sm text-gray-600" htmlFor="user-id-input">
            Kullanıcı ID
          </label>
          <input
            id="user-id-input"
            className="w-96 rounded border px-3 py-1.5 text-sm"
            value={userIdInput}
            onChange={(e) => setUserIdInput(e.target.value)}
            placeholder="data/generate_dummy.py ile üretilen bir kullanıcı UUID'si"
          />
        </div>
        <button type="submit" className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white">
          Yükle
        </button>
      </form>

      {!userId && (
        <p className="text-gray-500">
          Portföyü görmek için bir kullanıcı ID girin (DB'de <code>users</code> tablosundan alınabilir).
        </p>
      )}
      {userId && isLoading && <p className="text-gray-500">Yükleniyor...</p>}
      {userId && isError && <p className="text-red-600">{(error as Error).message}</p>}

      {data && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg bg-white p-4 shadow">
            <h2 className="mb-3 font-semibold text-gray-900">Varlık Dağılımı</h2>
            <div className="mb-4 grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-gray-500">Toplam Değer</div>
                <div className="text-lg font-semibold">{formatCurrency(data.total_value)}</div>
              </div>
              <div>
                <div className="text-gray-500">Kâr/Zarar</div>
                <div
                  className={`text-lg font-semibold ${
                    data.total_gain_loss.amount >= 0 ? "text-green-600" : "text-red-600"
                  }`}
                >
                  {formatCurrency(data.total_gain_loss.amount)} ({data.total_gain_loss.percent}%)
                </div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={data.allocation}
                  dataKey="value"
                  nameKey="asset_class"
                  outerRadius={100}
                  label={(entry) => ASSET_CLASS_LABELS[entry.asset_class as AssetClass]}
                >
                  {data.allocation.map((item) => (
                    <Cell key={item.asset_class} fill={ASSET_CLASS_COLORS[item.asset_class]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, _name, item) => [
                    formatCurrency(value),
                    ASSET_CLASS_LABELS[item.payload.asset_class as AssetClass],
                  ]}
                />
                <Legend formatter={(value: string) => ASSET_CLASS_LABELS[value as AssetClass] ?? value} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="flex h-[420px] flex-col rounded-lg bg-white p-4 shadow">
            <h2 className="mb-2 font-semibold text-gray-900">Sohbet</h2>
            <ChatBox userId={userId} />
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
