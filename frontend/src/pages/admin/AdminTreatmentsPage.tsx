import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { diseasesApi, treatmentsApi } from "@/lib/endpoints/knowledgeBase";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import type { TreatmentCategory, TreatmentResponseSchema } from "@/types/api";
import { ApiError } from "@/types/api";

interface TreatmentFormState {
  category: TreatmentCategory;
  instructions: string;
  safety_notes: string;
  source_citation: string;
  authority_referral_only: boolean;
}

const EMPTY_FORM: TreatmentFormState = {
  category: "organic",
  instructions: "",
  safety_notes: "",
  source_citation: "",
  authority_referral_only: false,
};

export default function AdminTreatmentsPage() {
  const { t } = useLocale();
  const [selectedDiseaseId, setSelectedDiseaseId] = useState<string>("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editing, setEditing] = useState<TreatmentResponseSchema | null>(null);
  const [form, setForm] = useState<TreatmentFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const diseases = useAsync(() => diseasesApi.list({ page: 1, page_size: 100 }), []);
  const treatments = useAsync(
    () => (selectedDiseaseId ? treatmentsApi.listForDisease(selectedDiseaseId) : Promise.resolve({ items: [] })),
    [selectedDiseaseId]
  );

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEdit = (tr: TreatmentResponseSchema) => {
    setEditing(tr);
    setForm({
      category: tr.category,
      instructions: tr.instructions,
      safety_notes: tr.safety_notes ?? "",
      source_citation: tr.source_citation ?? "",
      authority_referral_only: tr.authority_referral_only,
    });
    setFormError(null);
    setIsModalOpen(true);
  };

  const dosageMissing =
    form.category === "chemical" && !form.authority_referral_only && !form.source_citation.trim();

  const handleSave = async () => {
    setFormError(null);
    if (!selectedDiseaseId) {
      setFormError("Select a disease first.");
      return;
    }
    if (!form.instructions.trim()) {
      setFormError("Instructions are required.");
      return;
    }
    if (dosageMissing) {
      setFormError(t.admin.dosageRequired);
      return;
    }

    setIsSaving(true);
    const payload = {
      disease_id: selectedDiseaseId,
      category: form.category,
      instructions: form.instructions.trim(),
      safety_notes: form.safety_notes.trim() || undefined,
      source_citation: form.source_citation.trim() || undefined,
      authority_referral_only: form.authority_referral_only,
    };

    try {
      if (editing) {
        await treatmentsApi.update(editing.id, payload);
      } else {
        await treatmentsApi.create(payload);
      }
      setIsModalOpen(false);
      treatments.refetch();
    } catch (err) {
      if (err instanceof ApiError && err.code === "DOSAGE_SOURCE_REQUIRED") {
        setFormError(t.admin.dosageRequired);
      } else {
        setFormError(err instanceof ApiError ? err.message : t.common.unknownError);
      }
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-ink">{t.admin.treatmentsTitle}</h1>

      {diseases.status === "loading" && <PageLoader label={t.common.loading} />}
      {diseases.status === "error" && <ErrorState message={errorMessage(diseases.error)} onRetry={diseases.refetch} />}

      {diseases.status === "success" && (
        <div className="flex flex-wrap items-end gap-3">
          <Select
            label="Disease"
            value={selectedDiseaseId}
            onChange={(e) => setSelectedDiseaseId(e.target.value)}
            className="min-w-[16rem]"
          >
            <option value="">Select a disease…</option>
            {diseases.data.items.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
          <Button disabled={!selectedDiseaseId} onClick={openCreate}>
            {t.admin.addTreatment}
          </Button>
        </div>
      )}

      {selectedDiseaseId && treatments.status === "loading" && <PageLoader label={t.common.loading} />}
      {selectedDiseaseId && treatments.status === "error" && (
        <ErrorState message={errorMessage(treatments.error)} onRetry={treatments.refetch} />
      )}
      {selectedDiseaseId && treatments.status === "success" && treatments.data.items.length === 0 && (
        <EmptyState title="No treatments yet" body="Add organic, chemical, or biological treatment guidance for this disease." />
      )}

      {selectedDiseaseId && treatments.status === "success" && treatments.data.items.length > 0 && (
        <div className="flex flex-col gap-3">
          {treatments.data.items.map((tr) => (
            <div key={tr.id} className="flex items-start justify-between gap-4 rounded-card border border-line bg-surface p-4">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-2">
                  <Badge tone="primary">{tr.category}</Badge>
                  <span className="text-xs text-muted">v{tr.version}</span>
                </div>
                <p className="text-sm text-ink">{tr.instructions}</p>
                {tr.source_citation && <p className="mt-1 text-xs italic text-muted">{tr.source_citation}</p>}
                {tr.authority_referral_only && <p className="mt-1 text-xs text-severity-moderate">Authority referral only</p>}
              </div>
              <Button variant="secondary" size="sm" onClick={() => openEdit(tr)}>
                {t.admin.editTreatment}
              </Button>
            </div>
          ))}
        </div>
      )}

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editing ? t.admin.editTreatment : t.admin.addTreatment}>
        <div className="flex flex-col gap-3.5">
          {formError && <Alert tone="error">{formError}</Alert>}

          <Select
            label={t.admin.category}
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value as TreatmentCategory })}
          >
            <option value="organic">{t.result.organic}</option>
            <option value="chemical">{t.result.chemical}</option>
            <option value="biological">{t.result.biological}</option>
          </Select>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-ink">{t.admin.instructions}</label>
            <textarea
              className="rounded-card border border-line bg-surface px-3.5 py-2.5 text-sm text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              rows={3}
              value={form.instructions}
              onChange={(e) => setForm({ ...form, instructions: e.target.value })}
            />
          </div>

          <Input
            label={`${t.result.safetyNotes} (${t.common.optional})`}
            value={form.safety_notes}
            onChange={(e) => setForm({ ...form, safety_notes: e.target.value })}
          />

          {form.category === "chemical" && (
            <>
              <Input
                label={t.admin.sourceCitation}
                placeholder="e.g. FAO Pesticide Guideline 2023, p.14"
                value={form.source_citation}
                onChange={(e) => setForm({ ...form, source_citation: e.target.value })}
                disabled={form.authority_referral_only}
              />
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={form.authority_referral_only}
                  onChange={(e) => setForm({ ...form, authority_referral_only: e.target.checked })}
                  className="h-4 w-4 rounded border-line text-primary focus:ring-primary"
                />
                {t.admin.authorityOnly}
              </label>
              {dosageMissing && <Alert tone="warning">{t.admin.dosageRequired}</Alert>}
            </>
          )}

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
    </div>
  );
}
