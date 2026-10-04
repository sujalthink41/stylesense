# 0003 — Defer choosing the object store until CP12

**Status:** Accepted (2026-10-04)

## Context
The spec named MinIO for uploads and try-on images. MinIO's free distribution of prebuilt images has changed recently, and nothing needs object storage before CP12.

## Decision
Leave object storage out of the stack until CP12. Then evaluate S3-compatible options (e.g. MinIO, Garage, SeaweedFS) behind a `Storage` port and record the choice in a new ADR.

## Consequences
- A smaller CP1 stack.
- Code depends on an S3-style port, so the choice stays swappable.
