"""
Presenters: domain entities -> API response schemas. Shared by the scans, plants,
and assistant routers so every endpoint describes an observation the same way.

Image URLs are signed, expiring media URLs (media_signer) minted only after the
calling router has verified access to the record.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from app.domain.entities.diagnosis import Diagnosis
from app.domain.entities.tracking import ObservationNote, PlantProfile
from app.domain.labels import display_label
from app.infrastructure.security.media_signer import sign_media_url
from app.interface.schemas.ai_analysis_schemas import (
    AiAnalysisSchema,
    AiAnalysisStatus,
    AnalysisUrgency,
    CvConsistency,
    GeminiAnalysisSchema,
)
from app.interface.schemas.diagnosis_schemas import (
    AreaMeasurementSchema,
    CandidateSchema,
    DecisionSchema,
    DecisionThresholdsSchema,
    DiagnosisResponse,
    DiagnosisSummarySchema,
    DifferentialSchema,
    DiseaseSchema,
    ExplanationSchema,
    HintSchema,
    ImageQualitySchema,
    ObservationNoteSchema,
    PestSchema,
    PlantProfileRefSchema,
    PlantProfileSchema,
    PlantSchema,
    RecommendationSchema,
    SegmentationSchema,
    TreatmentGroupSchema,
    TreatmentSchema,
    WeatherSchema,
)

PREVENTION_ADVICE = [
    "Remove and destroy clearly infected plant material.",
    "Avoid overhead irrigation late in the day and improve air circulation.",
    "Practice crop rotation and field sanitation where applicable.",
]


def _visible_label(d: Diagnosis) -> Optional[str]:
    """The model's top-1 label is stored for every observation (audit trail), but an
    inconclusive result deliberately names no condition, so it is not exposed."""
    return None if d.decision_status == "inconclusive" else d.predicted_label


def measurement_basis(d: Diagnosis) -> Optional[str]:
    if d.affected_area_pct is None:
        return None
    if d.has_segmentation_measurement:
        return "segmentation"
    return "legacy_attention_estimate"


def model_limitations(d: Diagnosis, model_info: Optional[dict]) -> List[str]:
    codes = ["single_photo_assessment", "pests_nutrients_stress_not_detected",
             "unknown_diseases_not_reliably_rejected"]
    if model_info and model_info.get("available") and not model_info.get("has_healthy_class"):
        codes.append("model_cannot_confirm_healthy")
    if measurement_basis(d) != "segmentation":
        codes.append("affected_area_not_measured")
    thresholds = (d.decision or {}).get("thresholds") or {}
    if thresholds and (not thresholds.get("calibrated") or thresholds.get("source") == "unvalidated_default"):
        codes.append("confidence_not_calibrated")
    if d.is_legacy:
        codes.append("legacy_observation")
    return codes


def ai_analysis_to_schema(diagnosis: Diagnosis) -> Optional[AiAnalysisSchema]:
    aa = diagnosis.ai_analysis
    if aa is None:
        return None  # Gemini disabled / not run for this scan — nothing to show, not an error state
    if aa.status != "ok":
        return AiAnalysisSchema(status=AiAnalysisStatus.UNAVAILABLE,
                                message=aa.message or "AI analysis temporarily unavailable.")
    return AiAnalysisSchema(
        status=AiAnalysisStatus.OK,
        analysis=GeminiAnalysisSchema(
            diagnosis_explanation=aa.diagnosis_explanation or "",
            observed_symptoms=aa.observed_symptoms,
            cv_consistency=CvConsistency(aa.cv_consistency) if aa.cv_consistency else CvConsistency.UNCERTAIN,
            confidence_assessment=aa.confidence_assessment or "",
            severity_explanation=aa.severity_explanation or "",
            treatment_guidance=aa.treatment_guidance,
            prevention_guidance=aa.prevention_guidance,
            environmental_risk=aa.environmental_risk or "",
            urgency=AnalysisUrgency(aa.urgency) if aa.urgency else AnalysisUrgency.LOW,
        ),
    )


def _treatment_schema(treatment_repo, disease_id) -> Optional[TreatmentSchema]:
    treatments = treatment_repo.get_current_for_disease(disease_id)
    if not treatments:
        return None
    groups = {"organic": None, "chemical": None, "biological": None}
    for t in treatments:
        instructions = t.instructions
        if t.category.value == "chemical" and not t.is_dosage_verified():
            instructions = "Please consult your local agricultural authority for verified dosage guidance."
        groups[t.category.value] = TreatmentGroupSchema(
            instructions=instructions, safety_notes=t.safety_notes, source_citation=t.source_citation)
    return TreatmentSchema(**groups)


def _candidates(d: Diagnosis, plant_repo, disease_repo) -> List[CandidateSchema]:
    out = []
    for c in (d.differential or {}).get("model_candidates", []):
        has_kb = False
        if plant_repo and disease_repo and c.get("plant") and c.get("condition"):
            plant = plant_repo.get_by_canonical_name(c["plant"])
            if plant is not None:
                has_kb = disease_repo.get_current_by_plant_and_name(plant.id, c["condition"]) is not None
        out.append(CandidateSchema(
            label=c.get("label"), display_name=display_label(c.get("label")), plant=c.get("plant"),
            condition=c.get("condition"), probability_pct=c.get("probability_pct"),
            cause_type=c.get("cause_type"), typical_parts=c.get("typical_parts") or [],
            symptom_patterns=c.get("symptom_patterns") or [],
            regulated_in_many_regions=bool(c.get("regulated_in_many_regions")), has_knowledge_base_entry=has_kb,
        ))
    return out


def diagnosis_to_response(d: Diagnosis, plant_repo=None, disease_repo=None, treatment_repo=None,
                          plant_profile: Optional[PlantProfile] = None,
                          model_info: Optional[dict] = None) -> DiagnosisResponse:
    plant_schema = disease_schema = treatment_schema = None
    disease = None
    prevention_advice: List[str] = []

    if plant_repo and d.plant_id:
        p = plant_repo.get_by_id(d.plant_id) if hasattr(plant_repo, "get_by_id") else None
        if p is None:
            p = next((x for x in plant_repo.list() if x.id == d.plant_id), None)
        if p:
            plant_schema = PlantSchema(name=p.canonical_name, scientific_name=p.scientific_name)

    if disease_repo and d.disease_id:
        disease = disease_repo.get_by_id(d.disease_id)
        if disease:
            disease_schema = DiseaseSchema(
                name=disease.name, type=disease.disease_type, description=disease.description,
                symptoms=disease.symptoms, causes=disease.causes, transmission_method=disease.transmission_method,
            )
            if treatment_repo:
                treatment_schema = _treatment_schema(treatment_repo, disease.id)
            prevention_advice = list(PREVENTION_ADVICE)

    decision_raw = d.decision or {}
    thresholds = decision_raw.get("thresholds") or {}
    decision = None
    if decision_raw:
        decision = DecisionSchema(
            status=decision_raw.get("status") or d.decision_status,
            top1_probability=decision_raw.get("top1_probability"),
            margin=decision_raw.get("margin"),
            normalized_entropy=decision_raw.get("normalized_entropy"),
            plant_identified=decision_raw.get("plant_identified"),
            plant_probability_mass=decision_raw.get("plant_probability_mass"),
            thresholds=DecisionThresholdsSchema(**{k: thresholds.get(k) for k in DecisionThresholdsSchema.model_fields})
            if thresholds else None,
        )

    explanation = None
    if d.explanation or d.heatmap_image_ref:
        ex = d.explanation or {}
        explanation = ExplanationSchema(
            method=ex.get("method") or ("grad_cam" if d.heatmap_image_ref else None),
            available=bool(ex.get("available", d.heatmap_image_ref is not None)) and d.heatmap_image_ref is not None,
            reason=ex.get("reason"), target_label=ex.get("target_label"),
            image_url=sign_media_url(d.heatmap_image_ref),
        )

    seg = d.segmentation or {}
    segmentation = None
    if seg or not d.is_legacy:
        meas = seg.get("measurement")
        segmentation = SegmentationSchema(
            status=seg.get("status", "unavailable"), reason=seg.get("reason"), method=seg.get("method"),
            model_version=seg.get("model_version"),
            measurement=AreaMeasurementSchema(**{k: meas.get(k) for k in AreaMeasurementSchema.model_fields
                                                 if meas.get(k) is not None}) if meas else None,
            severity={k: v for k, v in (seg.get("severity") or {}).items() if isinstance(v, (str, type(None)))},
            overlay_url=sign_media_url(d.segmentation_overlay_ref),
            mask_url=sign_media_url(d.segmentation_mask_ref),
        )

    differential = None
    if d.differential:
        diff = d.differential
        differential = DifferentialSchema(
            version=diff.get("version"), taxonomy_version=diff.get("taxonomy_version"),
            model_candidates=_candidates(d, plant_repo, disease_repo),
            also_consider=diff.get("also_consider") or [],
            not_assessable_by_model=diff.get("not_assessable_by_model") or [],
            follow_up_questions=diff.get("follow_up_questions") or [],
            answers=diff.get("answers") or {},
            hints=[HintSchema(**h) for h in diff.get("hints") or []],
            expert_review_recommended=bool(diff.get("expert_review_recommended")),
            expert_review_reasons=diff.get("expert_review_reasons") or [],
            regulated_candidates=diff.get("regulated_candidates") or [],
        )

    quality = None
    if d.image_quality:
        q = d.image_quality
        quality = ImageQualitySchema(status=q.get("status", "ok"), issues=q.get("issues") or [],
                                     metrics=q.get("metrics") or {}, version=q.get("version"))

    original_url = sign_media_url(d.original_image_ref)
    return DiagnosisResponse(
        diagnosis_id=str(d.id),
        status="completed",
        plant=plant_schema,
        disease=disease_schema,
        confidence_score=d.confidence_score,
        severity_level=d.severity_level.value if d.severity_level else None,
        affected_area_pct=d.affected_area_pct,
        healthy_area_pct=d.healthy_area_pct,
        heatmap_image_url=sign_media_url(d.heatmap_image_ref),
        roi_image_url=original_url,
        original_image_url=original_url,
        low_confidence_flag=d.low_confidence_flag,
        pests_detected=[PestSchema(name=p.pest_name, confidence=p.confidence, bbox=p.bbox)
                        for p in d.pest_detections],
        treatment=treatment_schema,
        recovery_probability=disease.recovery_probability if disease else None,
        estimated_recovery_time=disease.estimated_recovery_time if disease else None,
        prevention_advice=prevention_advice,
        weather=(WeatherSchema(
            temperature_c=d.weather_snapshot.temperature_c, humidity_pct=d.weather_snapshot.humidity_pct,
            wind_speed_kmh=d.weather_snapshot.wind_speed_kmh,
            rain_probability_pct=d.weather_snapshot.rain_probability_pct, uv_index=d.weather_snapshot.uv_index,
        ) if d.weather_snapshot else None),
        recommendation=(RecommendationSchema(
            irrigation_advice=d.recommendation.irrigation_advice,
            spraying_advice=d.recommendation.spraying_advice,
            fertilizer_advice=d.recommendation.fertilizer_advice,
        ) if d.recommendation else None),
        report_url=f"/api/v1/reports/{d.id}" if d.report else None,
        diagnosed_at=d.diagnosed_at,
        ai_analysis=ai_analysis_to_schema(d),
        decision_status=d.decision_status or "legacy",
        is_legacy=d.is_legacy,
        predicted_label=_visible_label(d),
        predicted_display_name=display_label(_visible_label(d)),
        decision=decision,
        image_quality=quality,
        explanation=explanation,
        segmentation=segmentation,
        severity_method=d.severity_method,
        measurement_basis=measurement_basis(d),
        differential=differential,
        model_version=d.model_version,
        pipeline_version=d.pipeline_version,
        plant_profile=PlantProfileRefSchema(id=str(plant_profile.id), name=plant_profile.name)
        if plant_profile else None,
        limitations=model_limitations(d, model_info),
    )


def diagnosis_to_summary(d: Diagnosis, plant_names: Optional[dict] = None,
                         disease_names: Optional[dict] = None, profile_names: Optional[dict] = None
                         ) -> DiagnosisSummarySchema:
    plant_names = plant_names or {}
    disease_names = disease_names or {}
    profile_names = profile_names or {}
    return DiagnosisSummarySchema(
        id=str(d.id),
        plant=plant_names.get(d.plant_id) or (str(d.plant_id) if d.plant_id else None),
        disease=disease_names.get(d.disease_id) or (str(d.disease_id) if d.disease_id else None),
        severity_level=d.severity_level.value if d.severity_level else None,
        confidence_score=d.confidence_score,
        thumbnail_url=sign_media_url(d.original_image_ref),
        diagnosed_at=d.diagnosed_at,
        decision_status=d.decision_status or "legacy",
        predicted_label=_visible_label(d),
        predicted_display_name=display_label(_visible_label(d)),
        plant_profile_id=str(d.plant_profile_id) if d.plant_profile_id else None,
        plant_profile_name=profile_names.get(d.plant_profile_id),
        affected_area_pct=d.affected_area_pct if d.has_segmentation_measurement else None,
        measurement_basis=measurement_basis(d),
        image_quality_status=(d.image_quality or {}).get("status"),
    )


def note_to_schema(n: ObservationNote, owner_user_id) -> ObservationNoteSchema:
    return ObservationNoteSchema(id=str(n.id), note_type=n.note_type, body=n.body, data=n.data or {},
                                 author_is_owner=(n.author_user_id == owner_user_id), created_at=n.created_at)


def profile_to_schema(p: PlantProfile) -> PlantProfileSchema:
    return PlantProfileSchema(
        id=str(p.id), name=p.name, crop_type=p.crop_type, variety=p.variety, planting_date=p.planting_date,
        location_label=p.location_label, growing_environment=p.growing_environment, notes=p.notes,
        archived=p.archived_at is not None, created_at=p.created_at, updated_at=p.updated_at,
        observation_count=p.observation_count, last_observed_at=p.last_observed_at,
        last_decision_status=p.last_decision_status, last_predicted_label=p.last_predicted_label,
        last_predicted_display_name=display_label(p.last_predicted_label),
    )


def name_maps(diagnoses: Iterable[Diagnosis], plant_repo, disease_repo) -> tuple:
    plant_names, disease_names = {}, {}
    for d in diagnoses:
        if d.plant_id and d.plant_id not in plant_names and plant_repo is not None:
            p = plant_repo.get_by_id(d.plant_id)
            plant_names[d.plant_id] = p.canonical_name if p else None
        if d.disease_id and d.disease_id not in disease_names and disease_repo is not None:
            dz = disease_repo.get_by_id(d.disease_id)
            disease_names[d.disease_id] = dz.name if dz else None
    return plant_names, disease_names
