# Onboarding Wave 1 — Four-real migration assessment (read-only)

**Generated:** `20260802T002551Z`
**Template:** `default_kuwait` (36 items)
**Applied changes:** no

## Rollups

- Missing vs template: **True**
- Obsolete vs template: **True**
- Conflicts: **True**
- Brian partial seed: **True**

## Talal Fadhli (`WATHEFNI-96550252254`)

- Live items: **6** → `bank_details, civil_id, education_cert, medical, passport, personal_photo`
- Null owner/category rows: **6**
- Missing (32): access_card_issued, account_access_created, app_invite_sent, asset_handover, attendance_device_id, civil_id_expiry, code_of_conduct_ack, company_policy_ack, department_assigned, emergency_contact, employment_contract, first_day_checklist, job_title_confirmed, medical_check, nda_signed, offer_letter, passport_expiry, payroll_status, personal_details_form, probation_end, reporting_manager_assigned, residence, residency_expiry, salary_allowances_confirmed, salary_transfer_details, shift_group_assigned, training_completed, uniform_ppe_issued, visa_article_type, work_location_assigned, work_permit, work_permit_expiry
- Obsolete (2): education_cert, medical
- Conflicts:
  - `bank_details` status=pending: bank policy: keep row but collect via ESS encrypted workflow (no plaintext)
  - `passport` status=pending: required live=True template=False; passport required on legacy; optional on default_kuwait

## Fouad Burhamad (`WATHEFNI-96566363363`)

- Live items: **6** → `bank_details, civil_id, education_cert, medical, passport, personal_photo`
- Null owner/category rows: **6**
- Missing (32): access_card_issued, account_access_created, app_invite_sent, asset_handover, attendance_device_id, civil_id_expiry, code_of_conduct_ack, company_policy_ack, department_assigned, emergency_contact, employment_contract, first_day_checklist, job_title_confirmed, medical_check, nda_signed, offer_letter, passport_expiry, payroll_status, personal_details_form, probation_end, reporting_manager_assigned, residence, residency_expiry, salary_allowances_confirmed, salary_transfer_details, shift_group_assigned, training_completed, uniform_ppe_issued, visa_article_type, work_location_assigned, work_permit, work_permit_expiry
- Obsolete (2): education_cert, medical
- Conflicts:
  - `bank_details` status=pending: bank policy: keep row but collect via ESS encrypted workflow (no plaintext)
  - `passport` status=pending: required live=True template=False; passport required on legacy; optional on default_kuwait

## mohammad alqattan (`WATHEFNI-96597727743`)

- Live items: **6** → `bank_details, civil_id, education_cert, medical, passport, personal_photo`
- Null owner/category rows: **6**
- Missing (32): access_card_issued, account_access_created, app_invite_sent, asset_handover, attendance_device_id, civil_id_expiry, code_of_conduct_ack, company_policy_ack, department_assigned, emergency_contact, employment_contract, first_day_checklist, job_title_confirmed, medical_check, nda_signed, offer_letter, passport_expiry, payroll_status, personal_details_form, probation_end, reporting_manager_assigned, residence, residency_expiry, salary_allowances_confirmed, salary_transfer_details, shift_group_assigned, training_completed, uniform_ppe_issued, visa_article_type, work_location_assigned, work_permit, work_permit_expiry
- Obsolete (2): education_cert, medical
- Conflicts:
  - `bank_details` status=received: bank policy: keep row but collect via ESS encrypted workflow (no plaintext)
  - `passport` status=pending: required live=True template=False; passport required on legacy; optional on default_kuwait

## unknown (`WATHEFNI-96599411617`)

- Live items: **0** → `none`
- Null owner/category rows: **0**
- Missing (36): access_card_issued, account_access_created, app_invite_sent, asset_handover, attendance_device_id, bank_details, civil_id, civil_id_expiry, code_of_conduct_ack, company_policy_ack, department_assigned, emergency_contact, employment_contract, first_day_checklist, job_title_confirmed, medical_check, nda_signed, offer_letter, passport, passport_expiry, payroll_status, personal_details_form, personal_photo, probation_end, reporting_manager_assigned, residence, residency_expiry, salary_allowances_confirmed, salary_transfer_details, shift_group_assigned, training_completed, uniform_ppe_issued, visa_article_type, work_location_assigned, work_permit, work_permit_expiry
- Obsolete (0): none
- Conflicts: none

## Policy

- Do **not** apply this assessment in Wave 1.
- Keep `WATHEFNI_ONBOARDING_SEED=off` and `WATHEFNI_ONBOARDING_HR_MUTATE=off`.
- Bank/IBAN collection stays on encrypted ESS; do not expand plaintext onboarding.
- Controlled backfill belongs to Wave 2 after GO.
