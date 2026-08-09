interface Tab {
  key: string;
  label: string;
}

export function Tabs({ tabs, active, onChange }: { tabs: Tab[]; active: string; onChange: (key: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 rounded-card border border-line bg-canvas p-1">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={`flex-1 rounded-[calc(theme(borderRadius.card)-2px)] px-3 py-2 text-sm font-medium transition-colors
            ${active === tab.key ? "bg-surface text-primary-dark shadow-sm" : "text-muted hover:text-ink"}`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
