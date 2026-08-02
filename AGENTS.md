# Tennis AI

## Project Goal

Build a production-ready, AI-powered tennis coaching application that remains maintainable, modular, and scalable.

Primary platform:

- Android using Flutter

Backend:

- FastAPI

Database:

- PostgreSQL

Development environment:

- GitHub Codespaces
- Dev Container
- OpenAI Codex CLI

---

## Project Structure

`/app`

Flutter application.

`/backend`

FastAPI backend.

`/infra`

Docker, PostgreSQL, and deployment configuration.

`/docs`

Project documentation.

Do not invent files or directories. Inspect the repository before referring to or creating a path, and follow established local conventions when they exist.

---

## Architecture Guidelines

- Keep responsibilities explicit and dependencies directed toward stable domain abstractions.
- Separate presentation, business logic, data access, infrastructure, and AI processing concerns.
- Prefer simple, maintainable designs over unnecessary abstractions.
- Keep public interfaces deliberate and backward-compatible unless a breaking change is explicitly requested.
- Avoid coupling the Flutter client to backend implementation details or the API layer to AI framework details.

---

## Development Rules

Always prefer small, safe, and focused changes.

- Search the repository before modifying existing code.
- Do not modify unrelated files or perform unnecessary refactoring.
- Preserve existing comments unless they are demonstrably incorrect or removal is requested.
- Preserve existing formatting and style unless a formatting change is requested or required for the implementation.
- Explain the expected impact before presenting code or making substantial changes.
- Never invent APIs, dependencies, filenames, schemas, or behavior. Verify them from the repository or authoritative documentation.
- Ask a concise question when requirements are materially unclear and cannot be resolved from repository context.

When implementing end-to-end functionality, use this sequence when applicable:

1. Backend API
2. Flutter client
3. Integration
4. Tests

---

## Flutter Rules

- Use Flutter with Material 3 for the Android application.
- Use Riverpod for dependency injection and state management.
- Organize application code with a feature-first folder structure.
- Use the repository pattern to isolate data sources from application and presentation code.
- Prefer immutable models and immutable state.
- Keep widgets focused on presentation and user interaction.
- Keep business logic out of widgets and separate from UI code.
- Make loading, empty, success, and error states explicit where relevant.

---

## FastAPI Rules

- Organize backend code into routers, services, repositories, and schemas.
- Use routers for HTTP concerns only.
- Use services for business logic and orchestration.
- Use repositories for persistence and data access.
- Use Pydantic schemas for request, response, and boundary validation.
- Use FastAPI dependency injection for shared services, repositories, authentication, and infrastructure concerns.
- Use asynchronous endpoints and asynchronous I/O throughout the request path. Do not introduce blocking operations into the event loop.
- Never place database access or AI implementation logic directly inside routers.

---

## Database Rules

- Use PostgreSQL only.
- Manage schema changes with Alembic migrations.
- Never manually modify the production schema.
- Do not use raw SQL unless the ORM or query layer cannot reasonably express the required operation or measured performance requires it.
- When raw SQL is necessary, parameterize it, document the reason, and cover it with tests where practical.
- Keep transaction boundaries explicit and maintain compatibility between application changes and migrations.

---

## AI Rules

- Support TensorFlow and/or PyTorch where appropriate for model development and inference.
- Use OpenCV for video and image processing where appropriate.
- Support ONNX for portable or optimized model inference when applicable.
- Keep AI, computer-vision, preprocessing, inference, and post-processing code separated from the FastAPI transport layer.
- Expose AI capabilities to the API through clear service interfaces.
- Keep model loading and expensive initialization out of per-request code paths.
- Document model assumptions, inputs, outputs, and preprocessing requirements.

---

## Git Rules

- Keep commits small, cohesive, and easy to review.
- Never rewrite Git history.
- Never force-push unless explicitly requested by the user.
- Do not discard or overwrite unrelated user changes.

---

## Testing

- Add focused unit tests for new or changed behavior whenever practical.
- Run relevant existing tests before completing a task whenever possible.
- Never knowingly break existing tests.
- Preserve existing test coverage and add regression tests for bug fixes when practical.
- Report tests that were run and any tests that could not be run.

---

## Code Quality

- Prefer readability and explicit names.
- Prefer maintainable solutions over clever implementations.
- Avoid unnecessary abstractions and speculative generalization.
- Avoid unnecessary refactoring.
- Preserve comments and formatting unless a change is requested or necessary.
- Keep changes minimal and scoped to the requested outcome.

---

## Security

- Never commit secrets, tokens, private keys, or credentials.
- Never hardcode credentials or environment-specific secrets.
- Prefer environment variables and established secret-management mechanisms.
- Validate untrusted input and avoid logging sensitive information.

---

## Performance

- Avoid premature optimization.
- Profile or measure before optimizing.
- Prefer clear, correct code until evidence identifies a meaningful bottleneck.
- Consider memory, startup, model-loading, database-query, and network costs when performance work is justified.

---

## AI Assistant Rules

Before modifying existing code:

1. Search the repository for the relevant implementation, conventions, and tests.
2. Explain the intended change and its impact.
3. Verify APIs, filenames, dependencies, and assumptions from available evidence.
4. Ask for clarification if a material requirement remains unclear.

Never invent APIs or filenames. Do not assume repository structure beyond what has been verified.

Response style:

- Be concise.
- Explain reasoning before code.
- Prefer maintainable solutions.
- Clearly state assumptions, verification performed, and any remaining limitations.

---

## Long-term Goal

Build a production-ready AI tennis coaching platform.

The codebase should remain maintainable, modular, secure, testable, and scalable as the Flutter application, FastAPI backend, PostgreSQL data layer, and AI capabilities evolve.


---

## Documentation and Configuration Workflow

Whenever documentation or project configuration files are modified, automatically:

1. Review the changes.
2. Stage only the modified documentation/configuration files.
3. Create an appropriate Git commit.
4. Push to the current branch.

This applies to:

- AGENTS.md
- README.md
- docs/**
- .devcontainer/**
- .editorconfig
- .gitignore
- configuration files

Do not wait for another instruction unless the user explicitly requests not to commit.

Never automatically commit application source code.

---

## Git Workflow

After completing an implementation:

1. Review the diff.
2. Keep commits atomic and easy to review.
3. Use meaningful commit messages.
4. Push only after the commit succeeds.

Never leave completed documentation or configuration changes uncommitted unless explicitly requested.

---

## Project Conventions

Prefer the following project layout whenever new modules are introduced.

Flutter

```
feature/
    presentation/
    application/
    domain/
    data/
```

FastAPI

```
backend/
    routers/
    services/
    repositories/
    schemas/
    models/
    core/
```

---

## AI Model Management

Never store trained model weights inside the Git repository.

Store models externally and load them through configuration.

Document:

- model version
- input format
- output format
- preprocessing
- postprocessing

---

## Flutter Code Generation

When using:

- freezed
- json_serializable
- riverpod_generator

Run build_runner whenever generated files require updating.

---

## Task Completion Checklist

Before considering a task complete:

1. Verify the implementation.
2. Report modified files.
3. Report tests performed.
4. Report remaining limitations.
5. Suggest the next logical task when appropriate.

---

## Development Priority

When making engineering decisions, prioritize in the following order:

1. Correctness
2. Maintainability
3. Readability
4. Simplicity
5. Performance
6. Optimization

---

## Repository Inspection

Before modifying any file:

1. Search the repository for existing implementations.
2. Follow existing coding patterns.
3. Reuse existing abstractions whenever practical.
4. Avoid duplicate implementations.
5. Verify filenames before creating new files.

Never assume repository structure.
Always inspect first.