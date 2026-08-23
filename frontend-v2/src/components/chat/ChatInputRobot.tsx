import { AnimatePresence, motion } from "framer-motion";
import { BRAND } from "@/utils/colors";
import { useTheme } from "@/context/ThemeContext";

interface ChatInputRobotProps {
  visible: boolean;
  thinking: boolean;
  leaning: boolean;
}

const SLIDE_TRANSITION = { duration: 0.45, ease: "easeOut" as const };

// Koyu temada figür bir kademe koyulaştırılıyor — BRAND'in (var(--color-brand),
// dark: #C4485A) bu küçük figür ölçeğinde fazla parlak durduğu bildirildi.
// Birincil buton/avatarla aynı aile: gövde en koyu, kafa bir tık açık, boyun
// (aşağıda, eskiden hardcoded #1749A8 mavi) en koyu "detay" tonunda.
const BODY_DARK = "#7A2B39";
const HEAD_DARK = "#8E3446";
const NECK_DARK = "#16141A";

function Eye({ cx, thinking, color }: { cx: number; thinking: boolean; color: string }) {
  return (
    <motion.circle
      cx={cx}
      cy={26}
      r={2.4}
      fill={color}
      style={{ originX: 0.5, originY: 0.5 }}
      animate={thinking ? { scaleY: [1, 1, 0.15, 1] } : { scaleY: 1 }}
      transition={
        thinking
          ? { duration: 2.2, repeat: Infinity, times: [0, 0.82, 0.9, 1], ease: "easeInOut" }
          : { duration: 0.15 }
      }
    />
  );
}

function ThinkingDot({ cx, delay, color }: { cx: number; delay: number; color: string }) {
  return (
    <motion.circle
      cx={cx}
      cy={70}
      r={3}
      fill={color}
      animate={{ opacity: [0.25, 1, 0.25] }}
      transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut", delay }}
    />
  );
}

/**
 * Input odaklandığında sohbet kutusunun üst kenarından beliren maskot.
 * Görünürlük AnimatePresence ile mount/unmount edilir (slide-up/slide-down);
 * "thinking" (yanıt bekleme) durumu bundan bağımsız ayrı bir state olarak
 * göz kırpma + alt noktalarla gösterilir.
 */
export function ChatInputRobot({ visible, thinking, leaning }: ChatInputRobotProps) {
  const headRotated = !thinking && leaning;
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const bodyColor = isDark ? BODY_DARK : BRAND;
  const headColor = isDark ? HEAD_DARK : BRAND;
  const neckColor = isDark ? NECK_DARK : "#1749A8";

  return (
    <AnimatePresence>
      {visible && (
        <motion.svg
          key="chat-input-robot"
          width="58"
          height="78"
          viewBox="0 0 58 78"
          fill="none"
          initial={{ opacity: 0, y: 22, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 22, scale: 0.9 }}
          transition={SLIDE_TRANSITION}
          className="pointer-events-none absolute z-20"
          style={{ right: 62, bottom: "100%", marginBottom: 8, transformOrigin: "bottom center" }}
        >
          <path d="M13 62c0-11 3-18 15-18s15 7 15 18" fill={bodyColor} />
          <rect x="20" y="40" width="16" height="11" rx="5" fill={neckColor} />
          {/* Baş, girilen metne "bakar" gibi hafifçe döner (leaning true olduğunda) */}
          <motion.g
            animate={{ rotate: headRotated ? 18 : 10, x: headRotated ? -1 : 0, y: headRotated ? 2 : 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            style={{ transformOrigin: "29px 23px" }}
          >
            <circle cx="29" cy="23" r="18" fill={headColor} />
            <rect x="13" y="13" width="32" height="21" rx="10.5" fill="#fff" />
            <Eye cx={22} thinking={thinking} color={headColor} />
            <Eye cx={36} thinking={thinking} color={headColor} />
            <path d="M22 31c1.9 1.8 11.1 1.8 13 0" stroke={bodyColor} strokeWidth="1.8" strokeLinecap="round" />
          </motion.g>
          {thinking && (
            <g>
              <ThinkingDot cx={18} delay={0} color={headColor} />
              <ThinkingDot cx={29} delay={0.18} color={headColor} />
              <ThinkingDot cx={40} delay={0.36} color={headColor} />
            </g>
          )}
        </motion.svg>
      )}
    </AnimatePresence>
  );
}
