import { PageHeading } from "@/components/common/PageHeading";
import { Button } from "@/components/common/Button";
import { Card } from "@/components/common/Card";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { AssetClassCards } from "@/components/portfolio/AssetClassCards";
import { HoldingsTable } from "@/components/portfolio/HoldingsTable";
import { AssetComparisonChart } from "@/components/portfolio/AssetComparisonChart";
import { usePortfolioData } from "@/hooks/usePortfolioData";

export function PortfolioPage() {
  const { data, loading, error, isDemoData, refetch } = usePortfolioData();

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
      <PageHeading
        kicker="Varlıklar"
        title="Portföy"
        description={
          loading
            ? "Portföy verisi yükleniyor…"
            : `${data.instrumentCount} enstrüman, ${data.assetClassCount} varlık sınıfı.`
        }
        actions={<Button>Yeni Pozisyon Ekle</Button>}
      />

      {/* Backend'in üç hata kodu üç FARKLI durumdur (bkz. DashboardPage,
          docs/API.md) — sunucunun gönderdiği metin Türkçe ve bu ayrımı
          taşıyor, olduğu gibi gösteriliyor. */}
      {error && <ErrorBanner message={error} onDismiss={refetch} />}

      {/* Gösterilen veri sunucudan gelmediyse bunu SÖYLEMEK zorundayız —
          uydurma rakamı gerçek sanmak bir finans ürününde en kötü hata
          modu (CLAUDE.md §4). */}
      {isDemoData && !loading && !error && (
        <div className="mb-6 rounded-xl border border-line bg-surface-elevated px-4 py-3 text-[13px] text-ink-muted dark:border-transparent">
          Bu ekranda <strong className="font-semibold">tasarım verisi</strong> gösteriliyor —
          sunucuya bağlanılamadı.
        </div>
      )}

      {/* Gerçek veri gelmeden içerik ÇİZİLMİYOR — aksi halde kartlar bir an
          "0 enstrüman" / boş tablo gösterirdi (bkz. DashboardPage'deki aynı
          gerekçe). Henüz bu sayfaya özel bir iskelet yok, o yüzden basit bir
          yükleniyor metni yeterli. */}
      {loading ? (
        <p className="m-0 py-10 text-center text-sm text-ink-faint">Yükleniyor…</p>
      ) : (
        <>
          <AssetClassCards assetClasses={data.assetClasses} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2.1fr_1fr]">
            <div>
              <HoldingsTable holdings={data.holdings} />
            </div>
            <div className="flex flex-col gap-4">
              <Card className="p-6">
                <AssetComparisonChart />
              </Card>
            </div>
          </div>
        </>
      )}
      </div>
    </div>
  );
}
