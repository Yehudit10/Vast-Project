# Services

This folder contains all microservices of the project, one subfolder per service.

## Structure
Each service should include:
- `src/` – service code
- `tests/` – unit/integration tests (pytest preferred)
- `Dockerfile` – container build
- `README.md` – short usage notes
- `requirements.txt`

## Naming
- Use lowercase folder names (e.g., `sensors`, `sound`, `aerial-image`, `api-gateway`).
- Keep service scope focused and independent.

## Contributing
When adding a new service:
1. Create a new subfolder here.
2. Follow the template above.
3. Document any special configuration in the service’s own `README.md`.
