import { Card } from "@/components/common/Card";

/**
 * Veri gelene kadar gösterilen yükleme iskeleti.
 *
 * NEDEN VAR: Dashboard'dan çıkıp geri dönüldüğünde hook yeniden mount
 * oluyor ve gerçek veri gelene kadar `mockDashboard` dönüyordu — ekranda
 * bir anlığına TASARIM VERİSİ (uydurma rakamlar) beliriyordu. Üstelik
 * "tasarım verisi gösteriliyor" uyarısı yükleme sırasında bastırıldığı
 * için o rakamlar uyarısız görünüyordu. Bir finans ürününde uydurma
 * rakamı gerçek sanmak en kötü hata modu (CLAUDE.md §4).
 *
 * Sıfır göstermek de çözüm değildi: "portföyünüz 0 ₺" yazmak, elimizde
 * olmayan bir bilgiyi iddia etmek olurdu (AK 2.7 / 5.5). İskelet hiçbir
 * şey iddia etmiyor — sadece "yükleniyor" diyor.
 *
 * Düzen gerçek sayfayla AYNI: kart sayısı, grid oranları ve yükseklikler
 * birebir eşleşiyor ki veri gelince sayfa zıplamasın.
 */
interface DashboardSkeletonProps {
  /** Hata sonrası `false`: yükleme bitti, nabız atmak yanıltıcı olurdu. */
  animated?: boolean;
}

export function DashboardSkeleton({ animated = true }: DashboardSkeletonProps) {
  return (
    <div
      aria-busy={animated}
      aria-label={animated ? "Portföy verisi yükleniyor" : "Portföy verisi gösterilemiyor"}
      className={animated ? "animate-pulse" : undefined}
    >
      <div className="mb-6 grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} className="p-[22px]">
            <div className="mb-3.5 h-[28px] w-2/5 rounded bg-line2" />
            <div className="h-[38px] w-4/5 rounded bg-line2" />
            <div className="mt-2.5 h-[20px] w-3/5 rounded bg-line2" />
          </Card>
        ))}
      </div>

      <div className="mb-6 grid grid-cols-1 items-start gap-6 lg:grid-cols-[1.65fr_1fr]">
        <Card className="p-[22px]">
          <div className="mb-4 h-[28px] w-1/3 rounded bg-line2" />
          <div className="h-[300px] rounded bg-line2" />
        </Card>
        <Card className="p-[22px]">
          <div className="mb-4 h-[28px] w-1/2 rounded bg-line2" />
          <div className="mx-auto h-[220px] w-[220px] rounded-full bg-line2" />
        </Card>
      </div>

      <Card className="p-[22px]">
        <div className="mb-4 h-[28px] w-1/4 rounded bg-line2" />
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="mb-3 h-[44px] rounded bg-line2" />
        ))}
      </Card>
    </div>
  );
}
