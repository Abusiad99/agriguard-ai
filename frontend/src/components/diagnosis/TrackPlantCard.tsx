import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { plantsApi } from "@/lib/endpoints/aiFeatures";
import { ApiError, type DiagnosisResponse } from "@/types/api";

/** "Track this plant" on a diagnosis: start a new tracked plant from this scan, or
 * attach the scan to one the user already tracks. */
export function TrackPlantCard({ diagnosis, onTracked }: { diagnosis: DiagnosisResponse; onTracked: () => void }) {
  const { t } = useLocale();
  const [name, setName] = useState(diagnosis.plant?.name ? `${diagnosis.plant.name}` : "");
  const [existing, setExisting] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const plants = useAsync(() => plantsApi.list({ status: "active", pageSize: 100 }), [diagnosis.diagnosis_id]);

  if (diagnosis.tracked_plant) {
    return (
      <Card>
        <CardHeader>
          <CardTitle icon="sprout">{t.track.title}</CardTitle>
        </CardHeader>
        <p className="text-sm text-ink">
          {t.track.trackedAs} <strong>{diagnosis.tracked_plant.name}</strong>
        </p>
        <Link to={`/plants/${diagnosis.tracked_plant.id}`} className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
          {t.track.openPlant}
          <span className="flip-rtl inline-flex"><Icon name="arrowRight" className="h-4 w-4" /></span>
        </Link>
      </Card>
    );
  }

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    setBusy(true);
    try {
      await action();
      onTracked();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.unknownError);
    } finally {
      setBusy(false);
    }
  };

  const options = plants.status === "success" ? plants.data.items : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle icon="sprout">{t.track.title}</CardTitle>
      </CardHeader>
      <p className="mb-4 text-sm leading-relaxed text-muted">{t.track.body}</p>
      {error && <div className="mb-3"><Alert tone="error">{error}</Alert></div>}
      <form className="flex flex-col gap-2" onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) void run(() => plantsApi.create({ name: name.trim(), crop: diagnosis.plant?.name ?? null, initial_diagnosis_id: diagnosis.diagnosis_id }));
      }}>
        <Input name="track-plant-name" label={t.track.plantName} value={name} maxLength={120} placeholder={t.track.namePlaceholder} onChange={(e) => setName(e.target.value)} />
        <Button type="submit" size="sm" isLoading={busy} disabled={!name.trim()}>{t.track.newPlant}</Button>
      </form>
      {options.length > 0 && (
        <form className="mt-4 flex flex-col gap-2 border-t border-ink/[0.07] pt-4" onSubmit={(e) => {
          e.preventDefault();
          if (existing) void run(() => plantsApi.linkScan(existing, diagnosis.diagnosis_id));
        }}>
          <Select name="track-existing-plant" label={t.track.existing} value={existing} onChange={(e) => setExisting(e.target.value)}>
            <option value="">{t.track.choosePlant}</option>
            {options.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          <Button type="submit" size="sm" variant="secondary" isLoading={busy} disabled={!existing}>{t.track.add}</Button>
        </form>
      )}
    </Card>
  );
}
