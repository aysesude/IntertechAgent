import { PaperBoatThinking } from "@/components/paper-boat/PaperBoat";

/**
 * UYUMLULUK KATMANI (compatibility shim).
 *
 * Eski `PaperBoatLoader` component'i, artık resmi `paper-boat` paketindeki
 * `PaperBoatThinking`'i sarmalıyor — böylece bu component'i import eden
 * mevcut yerler (chat mesaj listesi vb.) hiçbir değişiklik yapmadan
 * çalışmaya devam ediyor, görsel olarak sadece yeni/resmi gemi çizimini
 * kullanıyor olacaklar.
 *
 * Yeni kod yazıyorsan bu dosyayı değil, doğrudan
 * `@/components/paper-boat/PaperBoat`'tan `PaperBoatThinking`'i kullan —
 * bu dosya sadece geçiş kolaylığı için tutuluyor.
 */

type PaperBoatLoaderState = "thinking" | "reconnecting";

interface PaperBoatLoaderProps {
  /** Bekleme durumunda gösterilecek metin. Varsayılan: "VİRA düşünüyor…" */
  label?: string;
  /**
   * 'thinking'      -> normal bekleme göstergesi (gemi dalgada yüzer)
   * 'reconnecting'  -> AK-1.10: bağlantı kesildiğinde gemi durur, soluklaşır
   */
  state?: PaperBoatLoaderState;
  className?: string;
}

export const PaperBoatLoader: React.FC<PaperBoatLoaderProps> = ({
  label,
  state = "thinking",
  className = "",
}) => {
  const isReconnecting = state === "reconnecting";
  const displayLabel =
    label ?? (isReconnecting ? "Bağlantı bekleniyor…" : "VİRA düşünüyor…");

  return (
    <PaperBoatThinking
      label={displayLabel}
      showLabel
      // Bağlantı koptuğunda hareketi durdur ve soluklaştır — eski
      // component'in 'reconnecting' davranışıyla aynı.
      amplitude={isReconnecting ? 0 : 0.85}
      className={className}
      style={isReconnecting ? { opacity: 0.4 } : undefined}
    />
  );
};

export default PaperBoatLoader;
