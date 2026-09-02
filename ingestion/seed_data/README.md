# Seed data (synthetic — Phase 3)

Populated in Phase 3.

- `fhir/` — synthetic FHIR R4 resources (`Patient`, `Condition`, `Observation`,
  `MedicationRequest`) with realistic-but-fictional values, modeled after
  `aws-samples/sample-bedrock-agentcore-healthcare-s3vectors` sample format.
- `notes/` — 8–12 synthetic free-text clinical notes with intentionally
  clinically-interesting content (e.g. an adverse reaction to contrast dye phrased
  unusually, to make the multi-step retrieval demo meaningful).

No real PHI. All identifiers, names, dates, and MRNs are fabricated.
