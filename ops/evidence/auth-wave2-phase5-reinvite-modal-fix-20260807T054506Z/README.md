# Phase 5 — Re-invite modal fix

## What happened

After HR revoke, Re-invite did **not** create a new `hr_task_only` invite (no audit after revoke).

Cause: a **pending** invite already existed (from an earlier code issue). Re-invite hit `pending_activation_invite_exists` and opened a supersede confirm. Canceling that dialog returned **silently** — no success, no one-time code modal.

Not: invite reuse without disclosure. Not: successful create with a missing modal.

## Fix

1. Re-invite **auto-supersedes** any pending invite, then always shows success notice + one-time code modal.
2. HR revoke **supersedes pending invites** so old codes cannot activate after revoke and Re-invite starts clean.

Auth flow / Phase 6 unchanged.
