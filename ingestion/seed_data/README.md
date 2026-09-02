# Seed data (synthetic — Phase 3)

**No real PHI.** All names, MRNs (`MRN-00X000X`), phone numbers, addresses, dates,
and clinical details are fabricated.

## `fhir/` — 3 synthetic FHIR R4 collection Bundles

`patient-001` .. `patient-003`, each with `Patient`, `Condition` (ICD-10-CM
coded), `Observation` (LOINC), and `MedicationRequest` (RxNorm) resources.
`patient_scope` in the pipeline == the FHIR `Patient.id`.

## `notes/` — 10 synthetic free-text clinical notes + `manifest.jsonl`

`manifest.jsonl` has one line per note: `file`, `source_note_id`,
`patient_scope`, `patient_id`, `note_type`, `encounter_date`, `has_headers`.

- **8 headered** notes (HPI / Assessment / Plan / Medications / Hospital Course)
  exercise section-aware chunking; **2 headerless** (`note-003`, `note-009`,
  `note-010`) exercise the fixed-size fallback.
- The **contrast-dye adverse-reaction** thread (patient-001, `note-001` /
  `note-003` / `note-010`) is written with indirect phrasing ("went blotchy and
  tight in the throat", "hives after the dye study") so a naive keyword search
  misses it — this is the multi-step retrieval demo from SPEC §7.

Consumed by `python -m ingestion.pipeline` (see `scripts/seed_demo_data.sh`).
