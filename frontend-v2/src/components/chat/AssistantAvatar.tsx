import { Compass } from "lucide-react";

/**
 * Tek amblem, tek kaynak: AI Chat ekranındaki her yerde ("Vira Chat" mesaj
 * balonu, sohbet paneli başlığı, "VİRA düşünüyor" göstergesi, üst menü
 * sekmesi) aynı ikonun kullanıldığından emin olmak için buradan içe aktar.
 * İkonu değiştirmek gerekirse tek değişiklik noktası burasıdır.
 */
export const AssistantIcon = Compass;

type AssistantAvatarSize = "sm" | "md";

const SIZE_STYLES: Record<AssistantAvatarSize, { box: string; icon: number }> = {
  md: { box: "h-[34px] w-[34px] rounded-[10px]", icon: 17 },
  sm: { box: "h-7 w-7 rounded-[8px]", icon: 13 },
};

interface AssistantAvatarProps {
  size?: AssistantAvatarSize;
  className?: string;
}

export function AssistantAvatar({ size = "md", className = "" }: AssistantAvatarProps) {
  const { box, icon } = SIZE_STYLES[size];
  return (
    <span className={`grid shrink-0 place-items-center bg-brand text-white ${box} ${className}`}>
      <AssistantIcon size={icon} strokeWidth={2.2} />
    </span>
  );
}
