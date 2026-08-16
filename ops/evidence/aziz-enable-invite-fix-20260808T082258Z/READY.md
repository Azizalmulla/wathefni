# Aziz enable/invite fix — PASS

**Verdict:** PASS  
**Evidence:** `/Users/azizalmulla/Desktop/claw/ops/evidence/aziz-enable-invite-fix-20260808T082258Z`

## Invite
- **invite_id:** `f902ddd3-8423-4f5b-a186-414c7d455813`
- **status:** pending / delivery_status=delivered / channel=email
- **to:** azizalmulla16@gmail.com

## Delivery provider result
```json
{
  "channel": "email",
  "status": "sent",
  "recipient_email": "azizalmulla16@gmail.com",
  "external_message_id": "c8f49944-f4af-4eee-8d70-81ca5f709916",
  "provider": "postmark",
  "message_id": "c8f49944-f4af-4eee-8d70-81ca5f709916",
  "provider_accept_status": "accepted_by_provider",
  "visible_from": "hr@wathefni.ai",
  "ok": true
}
```

## Final canonical state
```json
{
  "app_access_enabled": true,
  "email": "azizalmulla16@gmail.com",
  "employment_status": "active",
  "department": "Internal QA",
  "selected_employee_keys": [
    "WATHEFNI-96599338566"
  ],
  "invitation_status": "delivered",
  "invite_id": "f902ddd3-8423-4f5b-a186-414c7d455813",
  "provider_result": {
    "channel": "outbound_layer",
    "status": "sent",
    "external_message_id": null,
    "send_result": null,
    "last_error": null,
    "recipient_email": "azizalmulla16@gmail.com"
  },
  "recent_invites": [
    {
      "invite_id": "f902ddd3-8423-4f5b-a186-414c7d455813",
      "status": "pending",
      "delivery_status": "delivered",
      "delivery_channel": "email",
      "idempotency_key": "access_enabled:WATHEFNI-96599338566:WATHEFNI:WATHEFNI-96599338566",
      "created_at": "2026-08-08 08:25:31.802188+00:00"
    },
    {
      "invite_id": "0a5d2f40-2a73-457a-857a-40f0461013fa",
      "status": "superseded",
      "delivery_status": "delivered",
      "delivery_channel": "email",
      "idempotency_key": null,
      "created_at": "2026-08-08 07:54:51.953430+00:00"
    },
    {
      "invite_id": "5748856a-c77f-44f3-8174-27df8cf7d2a1",
      "status": "redeemed",
      "delivery_status": "delivered",
      "delivery_channel": "email",
      "idempotency_key": null,
      "created_at": "2026-08-07 06:49:04.298762+00:00"
    }
  ],
  "mint_path": "set_employee_app_access_auto"
}
```

## Verification
- Aziz added to Setup Console selected employees
- app_access_enabled=true
- Exactly one fresh pending invite minted (idempotency key released from superseded row)
- Email-only edit: no reconcile, access stayed enabled
- Real department change: reconcile ran (desired=true, changed=false), access stayed enabled; department restored
