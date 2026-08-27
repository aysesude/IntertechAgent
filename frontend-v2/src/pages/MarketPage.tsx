import { PageHeading } from "@/components/common/PageHeading";
import { ErrorBanner } from "@/components/common/ErrorBanner";
import { MarketTicker } from "@/components/market/MarketTicker";
import { NewsFeed } from "@/components/market/NewsFeed";
import { InfluenceList } from "@/components/market/InfluenceList";
import { CalendarCard } from "@/components/market/CalendarCard";
import { useMarketData } from "@/hooks/useMarketData";

export function MarketPage() {
  const { data, loading, error, isDemoData, headlinesError, refetch } = useMarketData();

  return (
    <div className="relative min-h-screen">
      <div className="relative z-10">
        <PageHeading
          kicker="Piyasa"
          title="Haber Akışı"
          description={
            loading
              ? "Piyasa verisi yükleniyor…"
              : "Başlıklar BloombergHT son dakika akışından; göstergeler veritabanındaki son kapanışlardan."
          }
        />

        {error && <ErrorBanner message={error} onDismiss={refetch} />}

        {/* Gösterilen veri sunucudan gelmediyse bunu SÖYLEMEK zorundayız.
            Bu uyarı eskiden BU EKRANDA YOKTU: sayfa tamamen tasarım verisiyle
            doluyken "kaynaklardan derlenir" diyordu, yani uydurma rakamlar
            gerçek ve kaynaklı iddiasıyla gösteriliyordu — bir finans
            ürününde en kötü hata modu (CLAUDE.md §4). */}
        {isDemoData && !loading && !error && (
          <div className="mb-6 rounded-xl border border-line bg-surface-elevated px-4 py-3 text-[13px] text-ink-muted dark:border-transparent">
            Bu ekranda <strong className="font-semibold">tasarım verisi</strong> gösteriliyor —
            sunucuya bağlanılamadı.
          </div>
        )}

        {/* KISMİ DURUM: şerit geldi ama canlı gündem alınamadı. Ekranın
            tamamını karartmak yerine eksik olanı söylüyoruz (AK 5.5). */}
        {headlinesError && !isDemoData && (
          <div className="mb-6 rounded-xl border border-line bg-surface-elevated px-4 py-3 text-[13px] text-ink-muted dark:border-transparent">
            {headlinesError} Göstergeler ve portföy etkisi güncel.
          </div>
        )}

        <MarketTicker indicators={data.indicators} />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.9fr_1fr]">
          <div className="flex flex-col gap-3.5">
            <NewsFeed news={data.news} />
            {!loading && data.news.length === 0 && !headlinesError && (
              <p className="m-0 text-[13px] text-ink-faint">Şu an gösterilecek başlık yok.</p>
            )}
          </div>
          <div className="flex flex-col gap-4">
            <InfluenceList rows={data.influence} />
            <CalendarCard events={data.calendar} />
          </div>
        </div>
      </div>
    </div>
  );
}
