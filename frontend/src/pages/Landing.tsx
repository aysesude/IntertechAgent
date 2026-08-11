import { Link } from "react-router-dom";

type Agent = {
  ad: string;
  aciklama: string;
  durum: "hazir" | "yapim";
  renk: string;
};

const AJANLAR: Agent[] = [
  {
    ad: "Portföy Ajanı",
    aciklama:
      "İşlem geçmişini ve varlık dağılımını analiz eder, portföy özetini ve getiriyi hesaplar.",
    durum: "hazir",
    renk: "bg-blue-500",
  },
  {
    ad: "Piyasa Araştırma Ajanı",
    aciklama:
      "Finansal haberleri ve raporları RAG ile okur, gelişmelerin portföye etkisini yorumlar.",
    durum: "yapim",
    renk: "bg-emerald-500",
  },
  {
    ad: "Risk / Strateji Ajanı",
    aciklama:
      "Volatilite ve konsantrasyonu değerlendirir, yeniden dengeleme önerisi sunar.",
    durum: "yapim",
    renk: "bg-amber-500",
  },
  {
    ad: "Orchestrator",
    aciklama:
      "Sorunun niyetini tespit eder, ilgili ajanlara dağıtır ve yanıtları tek cevapta birleştirir.",
    durum: "hazir",
    renk: "bg-violet-500",
  },
];

const ADIMLAR = [
  { no: "1", baslik: "Soru sorulur", metin: "Kullanıcı sohbet ekranından doğal dilde soru sorar." },
  { no: "2", baslik: "Ajanlar çalışır", metin: "Orchestrator görevi dağıtır, ajanlar paralel çalışır." },
  { no: "3", baslik: "Veri MCP'den gelir", metin: "Sayısal değerler modelden değil, MCP araçlarından okunur." },
  { no: "4", baslik: "Yanıt akar", metin: "Cevap kaynaklarıyla birlikte anlık olarak ekrana yazılır." },
];

function Landing(): JSX.Element {
  return (
    <div className="mx-auto max-w-5xl">
      {/* Hero */}
      <section className="rounded-2xl border border-gray-200 bg-white px-8 py-14 text-center shadow-sm">
        <span className="inline-block rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-blue-700">
          InternTech 2026
        </span>

        <h1 className="mt-5 text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
          Akıllı Kişisel Finans Danışmanı
        </h1>

        <p className="mx-auto mt-4 max-w-2xl text-lg leading-relaxed text-gray-600">
          Portföyünüzü analiz eden, piyasa haberlerini okuyan ve risk değerlendirmesi
          yapan çoklu ajan mimarili bir yapay zeka asistanı.
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/dashboard"
            className="rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white transition hover:bg-blue-700"
          >
            Dashboard'a git
          </Link>
          <Link
            to="/chat"
            className="rounded-lg border border-gray-300 px-6 py-3 font-semibold text-gray-700 transition hover:bg-gray-50"
          >
            Asistana soru sor
          </Link>
        </div>
      </section>

      {/* Ajanlar */}
      <section className="mt-12">
        <h2 className="text-xl font-bold text-gray-900">Çoklu ajan mimarisi</h2>
        <p className="mt-1 text-sm text-gray-500">
          Her ajan kendi uzmanlık alanında çalışır, Orchestrator üzerinden haberleşir.
        </p>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {AJANLAR.map((ajan) => (
            <div
              key={ajan.ad}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className={`h-2.5 w-2.5 rounded-full ${ajan.renk}`} />
                  <h3 className="font-semibold text-gray-900">{ajan.ad}</h3>
                </div>
                <span
                  className={
                    ajan.durum === "hazir"
                      ? "shrink-0 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700"
                      : "shrink-0 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500"
                  }
                >
                  {ajan.durum === "hazir" ? "Çalışıyor" : "Yapım aşamasında"}
                </span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-gray-600">{ajan.aciklama}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Nasıl çalışır */}
      <section className="mt-12">
        <h2 className="text-xl font-bold text-gray-900">Nasıl çalışır</h2>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ADIMLAR.map((adim) => (
            <div key={adim.no} className="rounded-xl border border-gray-200 bg-white p-5">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-sm font-bold text-white">
                {adim.no}
              </span>
              <h3 className="mt-3 font-semibold text-gray-900">{adim.baslik}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-gray-600">{adim.metin}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Uyarı */}
      <section className="mt-12 rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h3 className="font-semibold text-amber-900">Bu bir yatırım tavsiyesi değildir</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-amber-800">
          Uygulama sentetik demo verisiyle çalışır. Üretilen analiz ve öneriler
          eğitim amaçlıdır, gerçek yatırım kararlarına dayanak oluşturmaz.
        </p>
      </section>

      <p className="mt-10 text-center text-xs text-gray-400">
        InternTech 2026 · Akıllı Kişisel Finans Danışmanı
      </p>
    </div>
  );
}

export default Landing;
