# Changelog

All notable changes to FastAPI-url will be documented in this file.

## [0.3.0] - 2026-09-15

### Added
- Link expiration: `POST /urls/shorten?expires_in_seconds=N` — expired links return `410 Gone` on redirect
- `expires_at` exposed in shorten/list responses
- Validation: non-positive `expires_in_seconds` rejected with 422
- 4 new tests (19 total)

## [0.1.0] - 2025-01-01

### Added
- URL shortener with FastAPI
- RESTful API
- CI/CD pipeline
- Docker support
- CodeQL security analysis
- OpenSSF Scorecard
