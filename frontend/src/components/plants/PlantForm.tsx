import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import { useLocale } from "@/context/LocaleContext";
import type { TrackedPlantInput } from "@/lib/endpoints/aiFeatures";
import type { TrackedPlant } from "@/types/aiFeatures";
import { apiErrorText } from "@/lib/apiErrorText";

/** Create/edit form for a tracked plant. The location is optional and private to
 * the owner (it is never shown on the outbreak map). */
export function PlantForm({ initial, onSubmit, onCancel }: {
  initial?: TrackedPlant;
  onSubmit: (body: TrackedPlantInput & { clear_location?: boolean }) => Promise<unknown>;
  onCancel: () => void;
}) {
  const { t, locale } = useLocale();
  const f = t.plants.form;
  const [name, setName] = useState(initial?.name ?? "");
  const [crop, setCrop] = useState(initial?.crop ?? "");
  const [species, setSpecies] = useState(initial?.species ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [lat, setLat] = useState(initial?.latitude != null ? String(initial.latitude) : "");
  const [lon, setLon] = useState(initial?.longitude != null ? String(initial.longitude) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const useMyLocation = () => {
    navigator.geolocation?.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(5));
        setLon(pos.coords.longitude.toFixed(5));
      },
      () => setError(t.common.unknownError),
    );
  };

  const submit = async () => {
    if (!name.trim()) {
      setError(f.nameRequired);
      return;
    }
    const hasLocation = lat.trim() !== "" && lon.trim() !== "";
    setError(null);
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        crop: crop.trim() || null,
        species: species.trim() || null,
        notes: notes.trim() || null,
        latitude: hasLocation ? Number(lat) : null,
        longitude: hasLocation ? Number(lon) : null,
        ...(initial && !hasLocation && initial.latitude != null ? { clear_location: true } : {}),
      });
    } catch (err) {
      setError(apiErrorText(err, t, locale));
      setBusy(false);
    }
  };

  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      {error && <Alert tone="error">{error}</Alert>}
      <Input name="plant-name" label={f.name} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} required />
      <div className="grid gap-3 sm:grid-cols-2">
        <Input name="plant-crop" label={f.crop} value={crop} maxLength={100} onChange={(e) => setCrop(e.target.value)} />
        <Input name="plant-species" label={f.species} value={species} maxLength={150} onChange={(e) => setSpecies(e.target.value)} />
      </div>
      <Textarea name="plant-notes" label={f.notes} value={notes} maxLength={4000} rows={3} onChange={(e) => setNotes(e.target.value)} />
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium text-ink">{f.location}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input name="plant-latitude" label={f.latitude} type="number" step="any" min={-90} max={90} value={lat} onChange={(e) => setLat(e.target.value)} />
          <Input name="plant-longitude" label={f.longitude} type="number" step="any" min={-180} max={180} value={lon} onChange={(e) => setLon(e.target.value)} />
        </div>
        <Button type="button" size="sm" variant="ghost" icon="pin" className="w-fit" onClick={useMyLocation}>{f.useMyLocation}</Button>
      </fieldset>
      <div className="mt-2 flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>{f.cancel}</Button>
        <Button type="submit" isLoading={busy}>{f.save}</Button>
      </div>
    </form>
  );
}
