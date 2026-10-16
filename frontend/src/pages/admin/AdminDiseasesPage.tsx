import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { diseasesApi } from "@/lib/endpoints/knowledgeBase";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input, Textarea } from "@/components/ui/Input";
import { IconTile, PageHeader } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
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
    <div className="flex flex-col gap-6 stagger">
      <PageHeader
        title={t.admin.diseasesTitle}
        actions={
          <Button icon="plus" onClick={openCreate}>
            {t.admin.addDisease}
          </Button>
        }
      />

      {diseases.status === "loading" && <PageLoader label={t.common.loading} />}
      {diseases.status === "error" && <ErrorState message={errorMessage(diseases.error)} onRetry={diseases.refetch} />}

      {diseases.status === "success" && diseases.data.items.length === 0 && (
        <EmptyState iconName="book" title="No diseases yet" body="Add the first knowledge-base entry to get started." />
      )}

      {diseases.status === "success" && diseases.data.items.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 stagger">
          {diseases.data.items.map((d) => (
            <div key={d.id} className="glass flex flex-col gap-4 rounded-panel p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <IconTile name={d.disease_type === "pest" ? "bug" : "microbe"} />
                  <div className="min-w-0">
                    <p className="truncate font-display text-[1.05rem] font-semibold text-ink">{d.name}</p>
                    {d.disease_type && <p className="text-xs capitalize text-muted">{d.disease_type}</p>}
                  </div>
                </div>
                <span className="shrink-0 rounded-lg bg-ink/[0.05] px-2 py-1 font-data text-xs font-medium text-muted">v{d.version}</span>
              </div>
              <p className="line-clamp-2 flex-1 text-sm leading-relaxed text-muted">{d.description}</p>
              <div>
                <Button variant="glass" size="sm" icon="pencil" onClick={() => openEdit(d)}>
                  {t.admin.editDisease}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editing ? t.admin.editDisease : t.admin.addDisease}>
        <div className="flex flex-col gap-4">
          {formError && <Alert tone="error">{formError}</Alert>}
          <Input
            label={t.admin.plantName}
            name="plant_canonical_name"
            placeholder="tomato, date_palm, apple…"
            value={form.plant_canonical_name}
            onChange={(e) => setForm({ ...form, plant_canonical_name: e.target.value })}
          />
          <Input label={t.admin.diseaseName} name="disease_name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input
            label="Disease type"
            name="disease_type"
            placeholder="fungal, bacterial, pest…"
            value={form.disease_type}
            onChange={(e) => setForm({ ...form, disease_type: e.target.value })}
          />
          <Textarea
            label={t.admin.description}
            id="disease_description"
            rows={3}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <Input label="Symptoms (comma-separated)" name="symptoms" value={form.symptoms} onChange={(e) => setForm({ ...form, symptoms: e.target.value })} />
          <Input label="Causes (comma-separated)" name="causes" value={form.causes} onChange={(e) => setForm({ ...form, causes: e.target.value })} />
          <Input
            label={`Transmission method (${t.common.optional})`}
            name="transmission_method"
            value={form.transmission_method}
            onChange={(e) => setForm({ ...form, transmission_method: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={`Recovery probability % (${t.common.optional})`}
              name="recovery_probability"
              type="number"
              min={0}
              max={100}
              value={form.recovery_probability}
              onChange={(e) => setForm({ ...form, recovery_probability: e.target.value })}
            />
            <Input
              label={`Recovery time (${t.common.optional})`}
              name="estimated_recovery_time"
              placeholder="2-3 weeks"
              value={form.estimated_recovery_time}
              onChange={(e) => setForm({ ...form, estimated_recovery_time: e.target.value })}
            />
          </div>

          <div className="mt-2 flex justify-end gap-2.5">
            <Button variant="ghost" onClick={() => setIsModalOpen(false)}>
              {t.admin.cancel}
            </Button>
            <Button icon="check" isLoading={isSaving} onClick={() => void handleSave()}>
              {t.admin.save}
            </Button>
          </div>
        </div>
      </Modal>

      {diseases.status === "success" && <Pagination page={page} totalPages={diseases.data.total_pages} onChange={setPage} />}
    </div>
  );
}
