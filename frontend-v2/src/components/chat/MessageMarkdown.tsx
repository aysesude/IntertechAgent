import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Ajan cevaplarını markdown olarak basar.
 *
 * NEDEN GEREKLİ: cevaplar başlık, tablo ve liste içeriyor (RAG dokümanlarından
 * ve portföy dökümlerinden geliyor). Düz metin basıldığında ekrana
 * "| Gösterge | 2026 Ç2 |" gibi ham sözdizimi düşüyor.
 *
 * `remarkGfm` tablo desteği için şart — temel react-markdown GFM tablolarını
 * kapsamıyor.
 *
 * NEDEN HER ETİKET ELLE TANIMLI: Tailwind'in preflight sıfırlaması başlık
 * boyutlarını, liste işaretlerini ve kalın/italik ayrımını siliyor. Tanımı
 * unutulan etiket ekranda görünmez hale geliyor — nitekim eski sürümde `ol`
 * unutulmuştu ve ajan numaralı liste yazdığında NUMARALAR HİÇ GÖRÜNMÜYORDU.
 */
const COMPONENTS = {
  table: (props: ComponentPropsWithoutRef<"table">) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...props} />
    </div>
  ),
  th: (props: ComponentPropsWithoutRef<"th">) => (
    <th
      className="border border-line px-2 py-1 text-left font-semibold dark:border-white/15"
      {...props}
    />
  ),
  td: (props: ComponentPropsWithoutRef<"td">) => (
    <td className="border border-line px-2 py-1 dark:border-white/15" {...props} />
  ),
  p: (props: ComponentPropsWithoutRef<"p">) => <p className="mb-2 last:mb-0" {...props} />,
  ul: (props: ComponentPropsWithoutRef<"ul">) => (
    <ul className="mb-2 list-disc pl-5 last:mb-0" {...props} />
  ),
  // Eski sürümdeki kusurun düzeltmesi — bkz. yukarıdaki not.
  ol: (props: ComponentPropsWithoutRef<"ol">) => (
    <ol className="mb-2 list-decimal pl-5 last:mb-0" {...props} />
  ),
  li: (props: ComponentPropsWithoutRef<"li">) => <li className="mb-0.5" {...props} />,
  h1: (props: ComponentPropsWithoutRef<"h1">) => (
    <h1 className="mb-1.5 mt-2 text-[15px] font-semibold first:mt-0" {...props} />
  ),
  h2: (props: ComponentPropsWithoutRef<"h2">) => (
    <h2 className="mb-1.5 mt-2 text-sm font-semibold first:mt-0" {...props} />
  ),
  h3: (props: ComponentPropsWithoutRef<"h3">) => (
    <h3 className="mb-1 mt-2 text-[13.5px] font-semibold first:mt-0" {...props} />
  ),
  strong: (props: ComponentPropsWithoutRef<"strong">) => (
    <strong className="font-semibold" {...props} />
  ),
  em: (props: ComponentPropsWithoutRef<"em">) => <em className="italic" {...props} />,
  // Arka plan dolgusu YOK: vurgu punto ve ağırlık farkıyla veriliyor.
  code: (props: ComponentPropsWithoutRef<"code">) => (
    <code className="font-mono text-[0.92em]" {...props} />
  ),
  a: (props: ComponentPropsWithoutRef<"a">) => (
    <a className="font-medium underline underline-offset-2" {...props} />
  ),
};

export function MessageMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
      {text}
    </ReactMarkdown>
  );
}
