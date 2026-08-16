# Wave 2A — Source index

Fetched / consulted 2026-08-02. Desk research; supplier interviews still pending.

## ZKTeco / BioTime

| Source | URL | Use |
|---|---|---|
| ZKBio Time API product page | https://zkteco.com/en/ZKBioTime_API/ZKBioTime_API | Official API product positioning |
| ZKBio Time 9.0 API User Manual (PDF mirror) | https://www.nzteco.co.nz/wp-content/uploads/2026/02/ZKBioTime-9.0-API_User-Manual_20240628.pdf | Token auth; `/iclock/api/transactions/`; terminals; employees |
| BioTime 9.5 product | https://www.zkteco.me/BioTime-9.5 | Push devices; private cloud; third-party HR API; OS/DB matrix |
| ERPGulf BioTime↔ERPNext notes | https://app.erpgulf.com/en/blog/blog-post-6 | Practical token + sync pattern (regional) |
| zkbiotime-go client notes | https://pkg.go.dev/github.com/Supavasinan/zkbiotime-go | API license gate (`IsNotOpenAPI`); Basic vs token |
| ADMS protocol (unofficial but widely used) | https://github.com/s0x90/zkteco-adms | `/iclock/cdata`, getrequest, registry |
| ADMS privacy caution | https://github.com/msaied/zkteco-php | ADMS can upload photos/biodata |
| Push protocol explainers | https://punchconnect.com/blog/zkteco-push-protocol-explained ; https://www.punchinn.com/integration-guide/zkteco | Device outbound ADMS to cloud |

## Hikvision

| Source | URL | Use |
|---|---|---|
| 3rd-party integration overview PDF | https://www.hikvision.com/content/dam/hikvision/vn/webinar/Thang3_Hikvision_Tich_Hop_He_Thong_Overview-of-3rd-Party-Integration.pdf | ISAPI vs HikCentral OpenAPI vs ISUP |
| T&A integrate solution PDF | http://www.hikvisioneurope.com/za/portal/portal/02-Technical%20Materials/04-Training%20materials/03-HIK-League%202022/Technical%28Thursday%29/20220526%20Hikvision%20T%26A%20integrate%20solution/20220526%20Hikvision%20T%26A%20integrate%20solution.pdf | AcsEvent search; alertStream punch fields; OpenAPI person/event; DB bridge |
| ISAPI best practices (community) | https://github.com/uchkunr/hikvision-best-practices | AcsEvent search; event codes |
| Hik-Connect OpenAPI | https://tpp.hikvision.com/products/HC-Integration | Cloud attendance search / events |

## Suprema

| Source | URL | Use |
|---|---|---|
| Integration options API/SDK/G-SDK | https://support.supremainc.com/en/support/solutions/articles/24000055240-possible-integration-options-biostar-2-api-sdk-and-g-sdk | Method map |
| BioStar 2 TA API intro | https://support.supremainc.com/en/support/solutions/articles/24000073529--biostar-2-ta-api-introduction-to-biostar-2-ta-api | Port /login; punch domain |
| Punch logs modified | https://support.supremainc.com/en/support/solutions/articles/24000076547--biostar-2-ta-api-search-for-punch-logs | Idempotent pull cursor |
| WebSocket real-time logs | https://support.supremainc.com/en/support/solutions/articles/24000022040--biostar-2-how-to-get-the-real-time-event-logs-through-web-socket-method | API lag 3–10s |
| G-SDK quick start | https://supremainc.github.io/g-sdk/csharp/quick/ | Finger.GetImage / templates risk |
| Template encryption notes | https://support.supremainc.com/en/support/solutions/articles/24000013983--biostar-2-personal-information-and-communication-security-encryption-tls | AES templates — still must not enter Wathefni |

## Anviz

| Source | URL | Use |
|---|---|---|
| CrossChex Cloud get records | https://community.anviz.com/t/how-to-use-api-to-get-the-records-from-the-crosschex-cloud/726 | Pull API |
| CrossChex API definition / webhooks | https://community.anviz.com/t/crosschex-cloud-api-definition/1139 | Webhook + SDK |

## Kuwait / regional market

| Source | URL | Use |
|---|---|---|
| KCS IBA Time and Attendance | https://www.kcs.com.kw/iba-time-and-attendance/ | Local platform; vendor list; contacts |
| KCS company profile 2025 PDF | https://www.kcs.com.kw/wp-content/uploads/2025/05/kcs_company_profile_2025.pdf | IBA + Lenel/Virdi/IDEMIA/ZK/Suprema; Hikvision CCTV |
| Ideal Information Suprema (KW) | LinkedIn Ideal Information Co. BioStation 3 Rafa Nadal Academy post | Suprema agent claim |
| UltraTech access control KW | https://utechkw.com/services/elv/access-control | ZKTeco/Suprema/HID installs |
| Stebilex Kuwait biometrics | https://stebilex.com/kuwait/biometrics-system-supplier-distributor/ | IDEMIA/VIRDI/Suprema |
| ScreenCheck ME Suprema | https://www.screencheckme.com/suprema-biometric-access-control-middle-east/ | Regional distributor |
| AIMS / MS Solution ZK Kuwait listing | https://mssolution.me/zkteco-distributor-in-kuwait | ZK distribution claim (verify) |

## Wathefni internal

| Source | Use |
|---|---|
| `wathefni-orchestrator/attendance_authority_wave1.py` | Canonical ingest: `source`, `source_event_id`, directions |
| Wave 1C evidence | Production synthetic authority already durable — connectors must feed it |
