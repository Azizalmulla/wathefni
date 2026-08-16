# Live consistency matrix — onboarding canonical state (20260806T200247Z)

Each cell is `completion state · satisfied/required · next-action owner`, read live
from that surface's own endpoint after the transition. All four must agree.
A completed employee leaves the still-onboarding queue by design.

| Transition                        | HR queue                  | HR drawer                 | Employee app              | Employee profile          | Bank item            |
|-----------------------------------|---------------------------|---------------------------|---------------------------|---------------------------|----------------------|
| T0 baseline (bank applied)        | completed · out of queue  | completed · 4/4 · none    | completed · 4/4 · none    | completed · 4/4 · none    | accepted             |
| T1 submitted (with HR)            | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | processing           |
| T2 returned (waiting on employee) | reopened · 3/4 · employee | reopened · 3/4 · employee | reopened · 3/4 · employee | reopened · 3/4 · employee | replacement_required |
| T3 resubmitted (with HR)          | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | processing           |
| T4 HR approved (pending payroll)  | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | processing           |
| T5 approved (awaiting apply)      | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | reopened · 3/4 · hr       | processing           |
| T6 applied (complete)             | completed · out of queue  | completed · 4/4 · none    | completed · 4/4 · none    | completed · 4/4 · none    | accepted             |

Checks proven: 46 · failed: 0

Employee-app grouping at the two states that matter:

- correction requested: {"your_actions": ["bank_details"], "being_reviewed": ["offer_letter"], "handled_by_others": [], "completed": ["civil_id", "personal_photo", "employment_contract"]}
- after Apply: {"your_actions": [], "being_reviewed": ["offer_letter"], "handled_by_others": [], "completed": ["civil_id", "personal_photo", "employment_contract", "bank_details"]}
