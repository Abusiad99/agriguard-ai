import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { diseasesApi, treatmentsApi } from "@/lib/endpoints/knowledgeBase";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input, Textarea } from "@/components/ui/Input";
import { IconTile, PageHeader } from "@/components/ui/Card";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Switch } from "@/components/ui/Switch";
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

const CATEGORY_ICON: Record<TreatmentCategory, IconName> = {
  organic: "leaf",
  chemical: "beaker",
  biological: "microbe",
};

export default function AdminTreatmentsPage() {
  const { t } = useLocale();
  const categoryLabel: Record<TreatmentCategory, string> = {
    organic: t.result.organic,
    chemical: t.result.chemical,
    biological: t.result.biological,
  };
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
    <div className="flex flex-col gap-6 stagger">
      <PageHeader title={t.admin.treatmentsTitle} />

      {diseases.status === "loading" && <PageLoader label={t.common.loading} />}
      {diseases.status === "error" && <ErrorState message={errorMessage(diseases.error)} onRetry={diseases.refetch} />}

      {diseases.status === "success" && (
        <div className="glass flex flex-wrap items-end gap-3 rounded-panel p-4">
          <div className="min-w-[16rem] flex-1">
            <Select label="Disease" name="disease" value={selectedDiseaseId} onChange={(e) => setSelectedDiseaseId(e.target.value)}>
              <option value="">Select a disease…</option>
              {diseases.data.items.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </div>
          <Button size="lg" icon="plus" disabled={!selectedDiseaseId} onClick={openCreate}>
            {t.admin.addTreatment}
          </Button>
        </div>
      )}

      {selectedDiseaseId && treatments.status === "loading" && <PageLoader label={t.common.loading} />}
      {selectedDiseaseId && treatments.status === "error" && (
        <ErrorState message={errorMessage(treatments.error)} onRetry={treatments.refetch} />
      )}
      {selectedDiseaseId && treatments.status === "success" && treatments.data.items.length === 0 && (
        <EmptyState iconName="beaker" title="No treatments yet" body="Add organic, chemical, or biological treatment guidance for this disease." />
      )}

      {selectedDiseaseId && treatments.status === "success" && treatments.data.items.length > 0 && (
        <div className="flex flex-col gap-3 stagger">
          {treatments.data.items.map((tr) => (
            <div key={tr.id} className="glass flex items-start gap-4 rounded-panel p-5">
              <IconTile name={CATEGORY_ICON[tr.category]} tone={tr.category === "chemical" ? "accent" : "primary"} />
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex flex-wrap items-center gap-2">
                  <Badge tone="primary">{categoryLabel[tr.category]}</Badge>
                  <span className="rounded-lg bg-ink/[0.05] px-2 py-0.5 font-data text-xs text-muted">v{tr.version}</span>
                  {tr.authority_referral_only && <Badge tone="moderate">Authority referral only</Badge>}
                </div>
                <p className="text-sm leading-relaxed text-ink">{tr.instructions}</p>
                {tr.source_citation && (
                  <p className="mt-2 flex items-center gap-1.5 text-xs italic text-muted">
                    <Icon name="book" className="h-3.5 w-3.5 shrink-0" />
                    {tr.source_citation}
                  </p>
                )}
              </div>
              <Button variant="glass" size="sm" icon="pencil" onClick={() => openEdit(tr)}>
                {t.admin.editTreatment}
              </Button>
            </div>
          ))}
        </div>
      )}

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editing ? t.admin.editTreatment : t.admin.addTreatment}>
        <div className="flex flex-col gap-4">
          {formError && <Alert tone="error">{formError}</Alert>}

          <Select
            label={t.admin.category}
            name="category"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value as TreatmentCategory })}
          >
            <option value="organic">{t.result.organic}</option>
            <option value="chemical">{t.result.chemical}</option>
            <option value="biological">{t.result.biological}</option>
          </Select>

          <Textarea
            label={t.admin.instructions}
            id="treatment_instructions"
            rows={3}
            value={form.instructions}
            onChange={(e) => setForm({ ...form, instructions: e.target.value })}
          />

          <Input
            label={`${t.result.safetyNotes} (${t.common.optional})`}
            name="safety_notes"
            value={form.safety_notes}
            onChange={(e) => setForm({ ...form, safety_notes: e.target.value })}
          />

          {form.category === "chemical" && (
            <>
              <Input
                label={t.admin.sourceCitation}
                name="source_citation"
                placeholder="e.g. FAO Pesticide Guideline 2023, p.14"
                value={form.source_citation}
                onChange={(e) => setForm({ ...form, source_citation: e.target.value })}
                disabled={form.authority_referral_only}
              />
              <Switch
                checked={form.authority_referral_only}
                onChange={(checked) => setForm({ ...form, authority_referral_only: checked })}
                label={t.admin.authorityOnly}
              />
              {dosageMissing && <Alert tone="warning">{t.admin.dosageRequired}</Alert>}
            </>
          )}

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
    </div>
  );
}
