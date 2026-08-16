# R6 EN / AR / RTL proof

R6-touched customer-critical Setup journeys are bilingual. R11 still owns the full product-wide Arabic audit.

| Journey | EN | AR | RTL |
|---|---|---|---|
| Effective-state labels | Enabled / Available but disabled / Unavailable in this deployment / Requires a dependency / Not permitted | مفعّل / متاح لكنه متوقف / غير متاح في هذا النشر / يتطلب اعتماداً / غير مسموح | Cards set `dir`/`lang` on Wave 5 + delivery |
| Wave 5 Intelligence card | Title, privacy threshold, fiscal month, enable/disable, failed-save reason | ذكاء الموارد البشرية + matching AR copy | `dir={isAr ? 'rtl' : 'ltr'}` |
| Notification delivery card | Preset + no-secrets copy | الإشعارات والتسليم | same |
| Comp / WFP / JA / Learning / Benefits / ER / Engagement | Enable/disable + honest usable/unavailable copy | Matching AR; env-gate lie removed | Existing Setup `uiLocale` |
| Dependency 409 | Job Architecture must be enabled first. | يجب تفعيل هيكل الوظائف أولاً. | Server messages |
| Ordinary HR 403 | Ordinary HR access does not include Setup authority. | صلاحية الموارد البشرية العادية لا تشمل إعداد الشركة. | Server messages |
| Kill-switch public reason | Unavailable in this deployment. | غير متاح في هذا النشر. | No env names |

Unit scan: Wave 5 card contains `ذكاء الموارد البشرية` and uses `SetupEffectiveStateBanner`.

Safe debt: pre-existing `ChannelPolicyCard` and some older Setup chrome remain English-first. That is R11, not new R6 English-only debt for the journeys R6 added.
