# Tekarai 0.14.0 — Enterprise Communication Platform

Phase 14 completes the unified Communication bounded context while retaining all Phase 8, 10 and 11 behavior.

## Added

- Reference-preserving, idempotent message forwarding with historical snapshots.
- Secure attachment preflight and enforced MIME/extension/size/checksum/malware validation.
- Server-issued tenant-bound attachment storage keys and data classification.
- Permission-aware unified search across messages, conversations, channels, attachments, meetings and transcripts.
- Offline batch synchronization with client-generated message UUIDs, immutable replay receipts and conflict reporting.
- Transactional retention preview/execution with immutable run records and active legal-hold exclusions.
- Recording storage-key, file-size and checksum metadata.
- Operational retention management command.
- Constant-query-count message hydration for mentions, reactions and attachments.

## API

New authenticated endpoints under `/api/v1/communication/`:

- `POST /attachments/preflight`
- `POST /messages/{messageId}/forward`
- `GET /search`
- `POST /sync`
- `POST /retention/runs`

## Database

Apply `communication.0005_phase14_completion`.

## Compatibility

Existing conversation, message, channel, call, meeting, signaling, presence, recording, transcription, AI intelligence, moderation, official communication, policy and legal-hold APIs remain available. New attachment submissions must include Phase 14 security metadata from the preflight workflow.
