# R5C historical proof

Current org / manager / Performance edits must not rewrite historical Talent truth. Proved:

| Record | How history is kept | Proof |
|---|---|---|
| Dimension evidence | Versioned facts; `include_history=True` | Journey A `history intact` |
| Potential | Versioned assessments; prior rows withdrawn, not deleted | Journey A + D `potential preserved after 9-box` |
| Performance evidence link | Append-only links; `becomes_potential=false` | Journey B |
| Talent review population | Frozen on prepare | Journey A `review prepared` |
| HiPo | New designation supersedes prior; prior row retained | Journey D explicit HiPo |
| Succession slate | Nominations + plan `row_version`; coverage facts | Journey C multi-successor slate |
| Target-specific readiness | Stored on each nomination, not a global score | Journey C `ready_now` vs `ready_lt_1y` |
| Employee aspiration | `employee_declared` fact; managers cannot write that source | Journey E |
| Module-off | Settings `enabled=false`; rows remain | `history preserved after disable` |

C5/C6 audit tables (`talent_profile_c5_audit`, `talent_succession_c6_audit`) record actor + reason on every governed write.

9-box projection is not stored as employee state, so changing inputs cannot overwrite potential or Performance.
