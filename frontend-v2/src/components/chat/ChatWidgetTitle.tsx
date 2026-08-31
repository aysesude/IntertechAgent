import { memo, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

const FULL_LETTERS = ["V", "i", "r", "a"];
const MORPHED_LETTERS = ["A", "i"];
const MORPH_DELAY_MS = 900;

// Harfler arasında ~60ms kademeli gecikme — hepsi aynı anda değil, sırayla
// hareket etsin diye. Materyal Design'ın standart "smooth" eğrisi.
const STAGGER_S = 0.06;
const EASE: [number, number, number, number] = [0.4, 0, 0.2, 1];

// Kalan harflerin (A, İ) yeniden konumlanması spring ile — doğal, yumuşak
// bir yerleşme hissi. Fade-out olan harfler (V, R) için ayrı, kısa bir tween.
// Stiffness düşürülüp damping artırıldı — yerleşme daha yavaş ve belirgin.
const LAYOUT_TRANSITION = { type: "spring" as const, stiffness: 140, damping: 24 };
const FADE_TRANSITION = { duration: 0.6, ease: EASE };

/**
 * Widget her açıldığında "Vira Chat" olarak başlar, kısa bir bekleme sonrası
 * V ve r harfleri fade-out olur; kalan A ve i harfleri "Ai Chat" biçiminde
 * yeniden konumlanır. Panel her açılışta yeniden mount edildiği için bu
 * bileşen de sıfırdan başlar — animasyon her açılışta bir kez oynar.
 *
 * `memo` BİLEREK var, props ALMASA BİLE: bu bileşen ChatWidget'ın (soru
 * gönderme/yanıt bekleme gibi) her state güncellemesinde de yeniden
 * render ediliyordu — kendi state'i (`morphed`) değişmese de framer-
 * motion'ın `layout` prop'u her render'da yeniden ölçüm yapıp, soru
 * sorulunca metnin gereksiz yere zıplamasına yol açıyordu. `memo` (props
 * her zaman `{}` olduğu için) bu bileşeni parent'tan TAMAMEN izole eder —
 * yalnızca kendi mount'unda bir kez animasyon oynar, başka hiçbir şey
 * onu yeniden render ettiremez.
 */
export const ChatWidgetTitle = memo(function ChatWidgetTitle() {
  const [morphed, setMorphed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMorphed(true), MORPH_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  const letters = morphed ? MORPHED_LETTERS : FULL_LETTERS;

  return (
    <div className="flex h-[18px] items-center text-sm font-semibold">
      <AnimatePresence mode="popLayout" initial={false}>
        {letters.map((char, index) => {
          const delay = index * STAGGER_S;
          return (
            <motion.span
              key={char.toLowerCase()}
              layout
              initial={false}
              exit={{ opacity: 0, y: -4 }}
              transition={{
                layout: { ...LAYOUT_TRANSITION, delay },
                opacity: { ...FADE_TRANSITION, delay },
                y: { ...FADE_TRANSITION, delay },
              }}
              className="inline-block"
            >
              {char}
            </motion.span>
          );
        })}
      </AnimatePresence>
      <span>&nbsp;Chat</span>
    </div>
  );
});
