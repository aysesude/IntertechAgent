import type { CalendarEvent } from "@/types/finance";
import { Card } from "@/components/common/Card";

interface CalendarCardProps {
  events: CalendarEvent[];
}

export function CalendarCard({ events }: CalendarCardProps) {
  return (
    <Card className="p-[22px]">
      <h2 className="font-display m-0 mb-1.5 text-base font-semibold">Takvim</h2>
      <p className="m-0 mb-4 text-[12.5px] text-ink-faint">Bu haftanın veri akışı</p>
      <div className="flex flex-col">
        {events.map((event, i) => (
          <div key={event.id} className={`flex gap-3.5 py-[11px] ${i < events.length - 1 ? "border-b border-line2 dark:border-transparent" : ""}`}>
            <span className="w-11 text-xs font-bold text-brand">{event.date}</span>
            <span className="flex-1 text-[13px] text-ink-soft">{event.description}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
