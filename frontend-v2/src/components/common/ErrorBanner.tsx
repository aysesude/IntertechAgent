import { AlertCircle } from "lucide-react";
import { XIcon } from "@/components/icons";

interface ErrorBannerProps {
  message: string;
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="animate-fadeUp mb-6 flex items-center gap-2.5 rounded-[10px] border border-danger/30 bg-danger-tint px-4 py-3.5 text-[13.5px] font-medium text-danger">
      <AlertCircle size={17} className="shrink-0" />
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Kapat" className="shrink-0 text-danger/70 hover:text-danger">
          <XIcon size={13} />
        </button>
      )}
    </div>
  );
}
