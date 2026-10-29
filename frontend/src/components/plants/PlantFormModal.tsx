import { useState, type FormEvent } from "react";
import { useLocale } from "@/context/LocaleContext";
import { plantsApi } from "@/lib/endpoints/plants";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Alert } from "@/components/ui/Alert";
import type { GrowingEnvironment, PlantProfile, PlantProfileInput } from "@/types/api";

const ENVIRONMENTS: GrowingEnvironment[] = ["field", "greenhouse", "indoor", "orchard", "nursery", "other"];

/** Create or edit a plant profile. Only the name is required. */
export function PlantFormModal({
  plant,
  onClose,
  onSaved,
}: {
  plant?: PlantProfile;
  onClose: () => void;
  onSaved: (p: PlantProfile) => void;
}) {
  const { t } = useLocale();
  const [form, setForm] = useState<PlantProfileInput>({
    name: plant?.name ?? "",
    crop_type: plant?.crop_type ?? "",
    variety: plant?.variety ?? "",
    planting_date: plant?.planting_date ?? "",
    location_label: plant?.location_label ?? "",
    growing_environment: plant?.growing_environment ?? null,
    notes: plant?.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof PlantProfileInput, value: string | null) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name?.trim()) return;
    setSaving(true);
    setError(null);
    const payload: PlantProfileInput = {
      name: form.name.trim(),
      crop_type: form.crop_type?.trim() || null,
      variety: form.variety?.trim() || null,
      planting_date: form.planting_date || null,
      location_label: form.location_label?.trim() || null,
      growing_environment: form.growing_environment || null,
      notes: form.notes?.trim() || null,
    };
    try {
      onSaved(plant ? await plantsApi.update(plant.id, payload) : await plantsApi.create(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.common.unknownError);
    } finally {
      setSaving(false);
    }
  };

  const optional = ` (${t.plants.optional})`;
  return (
    <Modal isOpen onClose={onClose} title={plant ? t.plants.edit : t.plants.add}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
        <Input label={t.plants.name} name="name" required maxLength={100} value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label={t.plants.cropType + optional} name="crop_type" maxLength={100} value={form.crop_type ?? ""}
            onChange={(e) => set("crop_type", e.target.value)} />
          <Input label={t.plants.variety + optional} name="variety" maxLength={100} value={form.variety ?? ""}
            onChange={(e) => set("variety", e.target.value)} />
          <Input label={t.plants.plantingDate + optional} name="planting_date" type="date" value={form.planting_date ?? ""}
            onChange={(e) => set("planting_date", e.target.value)} />
          <Select label={t.plants.environment + optional} name="growing_environment" value={form.growing_environment ?? ""}
            onChange={(e) => set("growing_environment", e.target.value || null)}>
            <option value="">—</option>
            {ENVIRONMENTS.map((env) => (
              <option key={env} value={env}>{t.plants.environments[env]}</option>
            ))}
          </Select>
        </div>
        <Input label={t.plants.location + optional} name="location_label" maxLength={200} value={form.location_label ?? ""}
          onChange={(e) => set("location_label", e.target.value)} />
        <Textarea label={t.plants.notes + optional} name="notes" rows={3} maxLength={2000} value={form.notes ?? ""}
          onChange={(e) => set("notes", e.target.value)} />
        {error && <Alert tone="error">{error}</Alert>}
        <div className="flex justify-end gap-2.5">
          <Button variant="ghost" onClick={onClose}>{t.common.cancel}</Button>
          <Button type="submit" icon="check" isLoading={saving} disabled={!form.name?.trim()}>
            {saving ? t.plants.saving : plant ? t.common.save : t.plants.create}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
