# Tennis AI

## Project Goal

Build an AI-powered tennis coaching application.

Primary platform:

- Android (Flutter)

Backend:

- FastAPI

Database:

- PostgreSQL

Development Environment:

- GitHub Codespaces
- Dev Container
- OpenAI Codex CLI

---

# Project Structure

/app
Flutter application

/backend
FastAPI backend

/infra
Docker, PostgreSQL and deployment

/docs
Documentation

---

# Development Rules

Always prefer small and safe changes.

Do not modify unrelated files.

Never delete comments unless requested.

Never reformat unrelated code.

When implementing new functionality:

1. Backend API
2. Flutter client
3. Integration
4. Test

---

# Flutter Rules

Use Material 3.

Use Riverpod for state management.

Prefer immutable models.

Avoid business logic inside Widgets.

---

# FastAPI Rules

Use async endpoints.

Use Pydantic models.

Separate:

- routers
- services
- repositories

Database access must not be placed inside routers.

---

# Database Rules

PostgreSQL only.

Always use migrations.

Never manually modify production schema.

---

# Git Rules

Keep commits small.

Never force push unless explicitly requested.

Never rewrite history.

---

# Testing

Run tests before completing a task whenever possible.

---

# Coding Style

Prefer readability.

Prefer explicit names.

Avoid unnecessary abstractions.

---

# AI Assistant Rules

When requirements are unclear:

Ask before implementing.

When modifying code:

Explain the impact.

Never invent APIs.

Never assume file names.

Search the repository first.

---

# Long-term Goal

Build a production-ready AI tennis coaching platform.

The codebase should remain maintainable, modular and scalable.
