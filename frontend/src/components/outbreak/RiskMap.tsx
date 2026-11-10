import { useEffect, useRef } from "react";
import { MapContainer, Rectangle, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import { RISK_COLORS, positiveRateColor } from "@/lib/aiFeatureUi";
import type { GeoArea, MapCell } from "@/types/aiFeatures";

export type MapLayerKind = "observed" | "predicted";

const toBounds = (b: GeoArea["bounds"]): LatLngBoundsExpression => [[b.south, b.west], [b.north, b.east]];

function ClickHandler({ onPoint }: { onPoint: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPoint(e.latlng.lat, e.latlng.lng) });
  return null;
}

/** Fit the view to the cells when the set of cells changes (not when the same cells
 * are reloaded, e.g. with a new estimate — that would undo the user's pan/zoom). */
function FitToCells({ cells }: { cells: MapCell[] }) {
  const map = useMap();
  const latest = useRef(cells);
  latest.current = cells;
  const key = cells.map((c) => c.area.id).join(",");
  useEffect(() => {
    const current = latest.current;
    if (!current.length) return;
    const south = Math.min(...current.map((c) => c.area.bounds.south));
    const west = Math.min(...current.map((c) => c.area.bounds.west));
    const north = Math.max(...current.map((c) => c.area.bounds.north));
    const east = Math.max(...current.map((c) => c.area.bounds.east));
    map.fitBounds([[south, west], [north, east]], { padding: [24, 24], maxZoom: 9 });
  }, [key, map]);
  return null;
}

/**
 * Grid-cell risk map (OpenStreetMap tiles, no API key). Only aggregated cells from the
 * API are drawn — no individual scan locations exist on the client.
 */
export function RiskMap({ cells, layer, selectedBounds, onSelectCell, onSelectPoint, labels }: {
  cells: MapCell[];
  layer: MapLayerKind;
  selectedBounds?: GeoArea["bounds"] | null;
  onSelectCell: (cell: MapCell) => void;
  onSelectPoint: (lat: number, lon: number) => void;
  labels: { map: string; inspections: string; positives: string; noPrediction: string; risk: (level: string) => string };
}) {
  // MapContainer doesn't pass aria-* attributes to its element, so a wrapper names the region.
  return (
    <div role="region" aria-label={labels.map}>
    <MapContainer center={[20, 10]} zoom={2} minZoom={2} worldCopyJump className="h-[28rem] w-full rounded-2xl sm:h-[34rem]"
                  scrollWheelZoom>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                 attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
      <ClickHandler onPoint={onSelectPoint} />
      <FitToCells cells={cells} />
      {cells.map((cell) => {
        const color = layer === "predicted"
          ? (cell.prediction ? RISK_COLORS[cell.prediction.risk_level] : "#9ca3af")
          : positiveRateColor(cell.positive_rate);
        return (
          <Rectangle key={cell.area.id} bounds={toBounds(cell.area.bounds)}
                     pathOptions={{ color, weight: 1, fillColor: color, fillOpacity: layer === "predicted" && !cell.prediction ? 0.12 : 0.45 }}
                     eventHandlers={{ click: (e) => { e.originalEvent.stopPropagation(); onSelectCell(cell); } }}>
            <Tooltip sticky>
              {layer === "predicted"
                ? (cell.prediction ? labels.risk(cell.prediction.risk_level) : labels.noPrediction)
                : `${labels.positives}: ${cell.positives} / ${labels.inspections}: ${cell.inspections}`}
            </Tooltip>
          </Rectangle>
        );
      })}
      {selectedBounds && (
        <Rectangle bounds={toBounds(selectedBounds)} pathOptions={{ color: "#1f2937", weight: 2.5, fill: false, dashArray: "6 4" }} />
      )}
    </MapContainer>
    </div>
  );
}
