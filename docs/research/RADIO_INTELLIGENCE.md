# Radio Intelligence: status BLOCKED (no data processed, no results)

**Not implemented.** The only radio source reachable through the project's data provider is OpenF1 `team_radio`, which returns links to Formula 1 broadcast audio. That audio is protected content: project rules forbid silently downloading, storing or re-serving it, and nothing was downloaded.

A text classifier over race-control messages would not be radio intelligence, so none was built under that name. (Race-control text is already used as context in the pace, strategy and replay modules.)

## Unblock criteria
1. Written permission or a licence covering audio download, transcription and model evaluation, or owner-recorded audio with consent; record it in `DATA_CONTRACTS.md`.
2. Transcripts must stay local and be treated as the provider's content; no redistribution of audio or full transcripts.
3. Evaluation by race (never random message split) against a keyword baseline; report ASR word-error rate on a hand-checked sample before any downstream claim.
4. UI labels every output as transcript-derived and shows the source link, not a copy.
