import { useEffect, useState } from "react";
import { AI_BALON_SINIFLARI } from "@/components/chat/ChatBubble";
import { MessageMarkdown } from "@/components/chat/MessageMarkdown";
import { useWordReveal } from "@/chat/useWordReveal";

/**
 * Sohbet açılışındaki karşılama.
 *
 * MESAJ DEĞİL, bilerek. `messages` dizisine sahte bir kayıt eklenseydi üç şey
 * bozulurdu:
 *
 *  - `downloadTranscript(messages, …)` ajanın hiç üretmediği bir metni deftere
 *    yazardı; o döküm bozuk yanıtları toplamak için kullanılıyor.
 *  - "Dökümü İndir" düğmesi `messages.length === 0` ile kapalı tutuluyor;
 *    boş sohbette aktifleşirdi.
 *  - Sunucudan sohbet geçmişi yüklenmeye başladığında (uç var, henüz
 *    kullanılmıyor) geri gelen kaydın üstüne ikinci bir karşılama binerdi.
 *
 * ÖNDE üretiliyor, arkada değil. Oturum ancak İLK KULLANICI MESAJIYLA doğuyor
 * (`get_or_create_session` yalnızca `/api/chat` içinde çağrılıyor), dolayısıyla
 * karşılamayı DB'ye yazmak için sayfa açılışında yeni bir uç çağırmak ve
 * hiçbir şey sormadan çıkan herkes için çöp oturum satırı üretmek gerekirdi.
 * Üstelik kullanıcının gördüğü ilk şeyi ağ turuna bağlamak olurdu.
 *
 * Metin SABİT, LLM'e ürettirilmiyor: ürün adının ve kapsam cümlesinin her
 * açılışta aynı olması gerekiyor.
 *
 * Yatırım tavsiyesi ibaresi BURAYA girmez — sayfanın altında kalıcı olarak
 * duruyor ve karşılama finansal bir çıktı değil.
 */

/**
 * Karşılamanın işi sıcaklık değil, BEKLENTİ AYARLAMAK: ne yapabildiğini ve
 * neyi yapmayacağını baştan söylemek, "neden cevap vermedi" anının önüne
 * geçiyor. Son cümle "uydurmama" ilkesini kusur olarak değil söz olarak
 * sunuyor (CLAUDE.md §4).
 */
export function karsilamaMetni(ad: string | undefined): string {
  // Yalnızca İLK ad: `user.name` tam ad taşıyor ve "Merhaba Çağan Karan"
  // resmî bir yazışma gibi duruyor.
  const ilkAd = ad?.trim().split(/\s+/)[0];
  const hitap = ilkAd ? `Merhaba ${ilkAd}.` : "Merhaba.";

  return [
    hitap,
    "Ben VİRA, kişisel finans asistanınız.",
    "Portföyünüzün dağılımını, getirisini ve riskini gerçek verinizle inceleyebilir; hisse, döviz, altın ve fonlardaki gelişmeleri kaynağıyla birlikte anlatabilirim.",
    "Bilmediğim bir şey olursa tahmin yürütmem — açıkça söylerim.",
  ].join("\n\n");
}

/**
 * Karşılama bu sekmede bir kez açıldı mı.
 *
 * `ChatProvider` sayfaların ÜSTÜNDE duruyor (App.tsx), yani sohbet geçmişi
 * sayfa değiştirince yaşıyor; ama `AnimatePresence mode="wait"` sayfayı
 * unmount ettiği için ChatGreeting her dönüşte yeniden mount oluyordu.
 * Sonuç: on mesajlık bir sohbete geri döndüğünüzde karşılama, duran
 * mesajların ÜSTÜNDE kendini yeniden yazıyordu.
 *
 * Modül düzeyinde tutuluyor çünkü React state'i unmount'u aşamıyor — aynı
 * gerekçe `usePortfolioData`'daki paylaşılan önbellekte de yazılı.
 *
 * Tam sayfa yenilemede sıfırlanır ve karşılama yeniden açılır: o noktada
 * sohbet de sıfırlandığı için ilk karşılaşma yeniden başlıyor demektir.
 */
let karsilamaAcildi = false;

/** Modül bayrağını sıfırlar. YALNIZCA TESTLER İÇİN. */
export function __karsilamaDurumunuSifirla(): void {
  karsilamaAcildi = false;
}

export function ChatGreeting({ userName }: { userName?: string }) {
  const metin = karsilamaMetni(userName);

  // Bayrak initializer'da OKUNUR, orada YAZILMAZ. StrictMode geliştirmede
  // initializer'ı iki kez çağırıyor; mutasyon burada olsaydı ikinci çağrı
  // "zaten açıldı" görür ve animasyon geliştirmede hiç oynamazdı.
  const [bastanBasla] = useState(() => !karsilamaAcildi);
  useEffect(() => {
    karsilamaAcildi = true;
  }, []);

  // `bastanBasla`: metin ilk render'da tam elimizde ama yine de kelime kelime
  // açılsın — sohbetin geri kalanıyla aynı ritim. Kancanın varsayılanı
  // (tamamlanmış metni anında göstermek) geçmiş mesajlar için doğru, ilk
  // karşılaşmada değil.
  const gorunen = useWordReveal(metin, false, { bastanBasla });

  return (
    <div className="flex animate-fadeUp flex-col items-start gap-1">
      {/* Genişlik sınırı sarmalayıcıda, balonda değil — gerekçesi
          ChatBubble'da. Balon sınıfları da oradan geliyor ki iki asistan
          balonu birbirinden ayrışmasın. */}
      <div className="relative max-w-[90%]">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -left-2.5 -top-2.5 h-11 w-11 rounded-full bg-[color-mix(in_srgb,var(--color-brand)_25%,transparent)] blur-lg"
        />
        <div
          className={`relative w-fit rounded-[14px] px-[18px] py-3.5 text-sm leading-[1.65] ${AI_BALON_SINIFLARI}`}
        >
          <MessageMarkdown text={gorunen} />
        </div>
      </div>
    </div>
  );
}
