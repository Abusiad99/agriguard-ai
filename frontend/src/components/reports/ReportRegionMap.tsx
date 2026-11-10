import { MapContainer, Rectangle, TileLayer, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { RISK_COLORS } from "@/lib/aiFeatureUi";
import type { ReportContent } from "@/types/reports";
import type { RiskLevel } from "@/types/aiFeatures";

/** The region of an area report: aggregated grid cells only, coloured by the stored
 * risk estimate (grey when there is none). Loaded on demand (Leaflet). */
export default function ReportRegionMap({ map, labels }: {
  map: NonNullable<ReportContent["map"]>;
  labels: { inspections: string; positives: string; noEstimate: string; risk: (level: string) => string };
}) {
  if (!map.cells.length) return null;
  const south = Math.min(...map.cells.map((c) => c.area.bounds.south));
  const west = Math.min(...map.cells.map((c) => c.area.bounds.west));
  const north = Math.max(...map.cells.map((c) => c.area.bounds.north));
  const east = Math.max(...map.cells.map((c) => c.area.bounds.east));
  return (
    <MapContainer bounds={[[south, west], [north, east]]} className="h-80 w-full rounded-2xl print:hidden" scrollWheelZoom={false}>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                 attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
      {map.cells.map((c) => {
        const level = c.prediction?.risk_level as RiskLevel | undefined;
        const color = level ? RISK_COLORS[level] : "#9ca3af";
        const b = c.area.bounds;
        return (
          <Rectangle key={c.area.id} bounds={[[b.south, b.west], [b.north, b.east]]}
                     pathOptions={{ color: c.area.grid_key === map.selected ? "#111827" : color, weight: c.area.grid_key === map.selected ? 3 : 1,
                                    fillColor: color, fillOpacity: level ? 0.45 : 0.15 }}>
            <Tooltip sticky>
              {level ? labels.risk(level) : labels.noEstimate} · {labels.inspections}: {c.inspections ?? 0} · {labels.positives}: {c.positives ?? 0}
            </Tooltip>
          </Rectangle>
        );
      })}
    </MapContainer>
  );
}
