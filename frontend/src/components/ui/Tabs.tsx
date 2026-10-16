import type { ReactNode } from "react";
import { indicatorStyle, useSlidingIndicator } from "@/hooks/useSlidingIndicator";

interface Tab {
  key: string;
  label: string;
  icon?: ReactNode;
}

export function Tabs({ tabs, active, onChange }: { tabs: Tab[]; active: string; onChange: (key: string) => void }) {
  const { containerRef, rect } = useSlidingIndicator<HTMLDivElement>(active);

  return (
    <div ref={containerRef} role="tablist" className="relative flex gap-1 overflow-x-auto rounded-2xl bg-ink/[0.05] p-1 ring-1 ring-inset ring-ink/[0.06]">
      <span
        aria-hidden="true"
        className="absolute rounded-xl bg-surface shadow-soft ring-1 ring-ink/[0.06] transition-[transform,width,opacity] duration-500 ease-out-expo"
        style={indicatorStyle(rect)}
      />
      {tabs.map((tab) => {
        const isActive = active === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            data-indicator-item
            data-active={isActive}
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            className={`relative z-[1] flex flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-xl px-3.5 py-2 text-sm font-medium transition-colors duration-300
              ${isActive ? "text-primary-dark" : "text-muted hover:text-ink"}`}
          >
            {tab.icon}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
