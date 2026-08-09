import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { diseasesApi } from "@/lib/endpoints/knowledgeBase";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import type { DiseaseResponseSchema } from "@/types/api";
import { ApiError } from "@/types/api";

const PAGE_SIZE = 20;

interface DiseaseFormState {
  plant_canonical_name: string;
  name: string;
  disease_type: string;
  description: string;
  symptoms: string;
  causes: string;
  transmission_method: string;
  recovery_probability: string;
  estimated_recovery_time: string;
}

const EMPTY_FORM: DiseaseFormState = {
  plant_canonical_name: "",
  name: "",
  disease_type: "",
  description: "",
  symptoms: "",
  causes: "",
  transmission_method: "",
  recovery_probability: "",
  estimated_recovery_time: "",
};

function toFormState(d: DiseaseResponseSchema): DiseaseFormState {
  return {
    plant_canonical_name: "", // plant_id -> canonical name isn't resolvable from this schema alone; operator re-enters if changing plant
    name: d.name,
    disease_type: d.disease_type ?? "",
    description: d.description,
    symptoms: d.symptoms.join(", "),
    causes: d.causes.join(", "),
    transmission_method: d.transmission_method ?? "",
    recovery_probability: d.recovery_probability != null ? String(d.recovery_probability) : "",
    estimated_recovery_time: d.estimated_recovery_time ?? "",
  };
}

export default function AdminDiseasesPage() {
  const { t } = useLocale();
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<DiseaseResponseSchema | null>(null);
  const [form, setForm] = useState<DiseaseFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const diseases = useAsync(() => diseasesApi.list({ page, page_size: PAGE_SIZE }), [page]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEdit = (d: DiseaseResponseSchema) => {
    setEditing(d);
    setForm(toFormState(d));
    setFormError(null);
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    setFormError(null);
    if (!form.plant_canonical_name.trim() || !form.name.trim() || !form.description.trim()) {
      setFormError("Plant, name, and description are required.");
      return;
    }

    setIsSaving(true);
    const payload = {
      plant_canonical_name: form.plant_canonical_name.trim().toLowerCase().replace(/\s+/g, "_"),
      name: form.name.trim(),
      disease_type: form.disease_type.trim() || undefined,
      description: form.description.trim(),
      symptoms: form.symptoms.split(",").map((s) => s.trim()).filter(Boolean),
      causes: form.causes.split(",").map((c) => c.trim()).filter(Boolean),
      transmission_method: form.transmission_method.trim() || undefined,
      recovery_probability: form.recovery_probability ? Number(form.recovery_probability) : undefined,
      estimated_recovery_time: form.estimated_recovery_time.trim() || undefined,
    };

    try {
      if (editing) {
        await diseasesApi.update(editing.id, payload);
      } else {
        await diseasesApi.create(payload);
      }
      setIsModalOpen(false);
      diseases.refetch();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t.common.unknownError);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display text-2xl font-semibold text-ink">{t.admin.diseasesTitle}</h1>
        <Button onClick={openCreate}>{t.admin.addDisease}</Button>
      </div>

      {diseases.status === "loading" && <PageLoader label={t.common.loading} />}
      {diseases.status === "error" && <ErrorState message={errorMessage(diseases.error)} onRetry={diseases.refetch} />}

      {diseases.status === "success" && diseases.data.items.length === 0 && (
        <EmptyState title="No diseases yet" body="Add the first knowledge-base entry to get started." />
      )}

      {diseases.status === "success" && diseases.data.items.length > 0 && (
        <div className="flex flex-col gap-3">
          {diseases.data.items.map((d) => (
            <div key={d.id} className="flex items-start justify-between gap-4 rounded-card border border-line bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-display font-semibold text-ink">
                  {d.name} <span className="ms-1 text-xs font-normal text-muted">v{d.version}</span>
                </p>
                {d.disease_type && <p className="text-xs uppercase tracking-wide text-muted">{d.disease_type}</p>}
                <p className="mt-1.5 line-clamp-2 text-sm text-ink">{d.description}</p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => openEdit(d)}>
                {t.admin.editDisease}
              </Button>
            </div>
          ))}
        </div>
      )}

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editing ? t.admin.editDisease : t.admin.addDisease}>
        <div className="flex flex-col gap-3.5">
          {formError && <Alert tone="error">{formError}</Alert>}
          <Input
            label={t.admin.plantName}
            placeholder="tomato, date_palm, apple…"
            value={form.plant_canonical_name}
            onChange={(e) => setForm({ ...form, plant_canonical_name: e.target.value })}
          />
          <Input
            label={t.admin.diseaseName}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            label="Disease type"
            placeholder="fungal, bacterial, pest…"
            value={form.disease_type}
            onChange={(e) => setForm({ ...form, disease_type: e.target.value })}
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-ink">{t.admin.description}</label>
            <textarea
              className="rounded-card border border-line bg-surface px-3.5 py-2.5 text-sm text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              rows={3}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <Input
            label="Symptoms (comma-separated)"
            value={form.symptoms}
            onChange={(e) => setForm({ ...form, symptoms: e.target.value })}
          />
          <Input
            label="Causes (comma-separated)"
            value={form.causes}
            onChange={(e) => setForm({ ...form, causes: e.target.value })}
          />
          <Input
            label={`Transmission method (${t.common.optional})`}
            value={form.transmission_method}
            onChange={(e) => setForm({ ...form, transmission_method: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={`Recovery probability % (${t.common.optional})`}
              type="number"
              min={0}
              max={100}
              value={form.recovery_probability}
              onChange={(e) => setForm({ ...form, recovery_probability: e.target.value })}
            />
            <Input
              label={`Recovery time (${t.common.optional})`}
              placeholder="2-3 weeks"
              value={form.estimated_recovery_time}
              onChange={(e) => setForm({ ...form, estimated_recovery_time: e.target.value })}
            />
          </div>

          <div className="mt-2 flex justify-end gap-2.5">
            <Button variant="ghost" onClick={() => setIsModalOpen(false)}>
              {t.admin.cancel}
            </Button>
            <Button isLoading={isSaving} onClick={() => void handleSave()}>
              {t.admin.save}
            </Button>
          </div>
        </div>
      </Modal>

      {diseases.status === "success" && diseases.data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t.common.back}
          </Button>
          <span className="text-sm text-muted">
            {t.common.page} {diseases.data.page} {t.common.of} {diseases.data.total_pages}
          </span>
          <Button variant="ghost" size="sm" disabled={page >= diseases.data.total_pages} onClick={() => setPage((p) => p + 1)}>
            {t.common.next}
          </Button>
        </div>
      )}
    </div>
  );
}
