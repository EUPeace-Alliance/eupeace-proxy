# 🤝 Contributing to the EUPEACE Proxy Identifier

Thank you for your interest in contributing to the **EUPEACE Proxy Identifier**! This project provides central authentication and federated access infrastructure for the **EUPeace European University Alliance**.

Contributions from all partner universities and developers are welcome. To maintain high code quality, security, and stability, please review these guidelines before submitting issues or pull requests.

---

## 1. Code of Conduct

We are committed to providing a welcoming, inclusive, and professional environment for everyone. Please be respectful, constructive, and collaborative in all discussions, issues, and code reviews.

---

## 2. How to Contribute

### Reporting Bugs
If you identify a bug or unexpected behavior:
1. Search the existing issues and pull requests to ensure the problem has not already been reported.
2. Open a new issue with a clear, descriptive title.
3. Include:
   * A concise description of the observed issue vs. expected behavior.
   * Reproduction steps.
   * Environment details (Docker version, browser, target IdP entity ID if applicable).
   * Relevant sanitized logs from `docker compose logs web` (ensure no passwords or real session tokens are exposed).

### Suggesting Enhancements
Feature requests are welcomed:
1. Open an issue describing the proposed feature or improvement.
2. Detail the motivation, alliance use case, and proposed implementation design.
3. Discuss the concept with the maintainers before submitting large structural changes.

---

## 3. Git Workflow & Branching Strategy

The repository follows a feature-branch workflow based on the `main` branch.

### 1. Fork and Clone
```bash
git clone git@github.com:EUPeace-Alliance/eupeace-proxy.git
cd eupeace-proxy
```

### 2. Branch Naming Conventions
Always create a new branch from `main` using standard prefixes:
* `feat/<feature-name>`: New functionality (e.g., `feat/oidc-claims`)
* `fix/<bug-name>`: Bug fixes (e.g., `fix/mdq-timeout`)
* `refactor/<scope>`: Code restructuring without functional changes (e.g., `refactor/attribute-mapping`)
* `docs/<topic>`: Documentation updates (e.g., `docs/saml-endpoints`)
* `test/<scope>`: Adding or modifying test suites (e.g., `test/oauth2-gatekeeping`)
* `chore/<task>`: Tooling, dependency, or configuration updates

### 3. Commit Message Guidelines
This repository strictly enforces **Conventional Commits**:
```
<type>(<scope>): <short description in imperative present tense>
```

**Allowed types:**
* `feat`: A new feature or capability.
* `fix`: A bug fix.
* `refactor`: Code changes that neither fix a bug nor add a feature.
* `docs`: Documentation changes only.
* `test`: Adding missing tests or correcting existing tests.
* `chore`: Build process, dependencies, or auxiliary tool changes.

**Examples:**
* `feat: implement OAuth2 authorization gatekeeping and visibility policy enforcement`
* `refactor: change entity_id fields from URLField to CharField to support URNs`
* `fix: prevent browser caching and bfcache on sensitive views and logout`
* `docs: update SAML and OIDC endpoint references in README`

---

## 4. Coding & Security Standards

### Python & Django Best Practices
* **Python Compatibility:** Target Python 3.12+; adhere to **PEP 8** style guidelines.
* **Typing & Clean Code:** Write readable, modular code with descriptive variable names and helpful docstrings.
* **Database Models:**
  * When adding or updating models, generate clean migration files (`python manage.py makemigrations`).
  * Always provide descriptive `verbose_name` and `help_text` fields.
  * For entity identifiers that may accept both URLs and URNs (e.g., federated IdP entity IDs), use `CharField(max_length=500)` rather than `URLField`.
* **Templates & UI:**
  * Utilize Bootstrap 5.3 markup consistent with existing templates in `core/templates/`.
  * Maintain responsive behavior for mobile, tablet, and desktop viewports.
  * Keep branding consistent with the official EUPeace visual identity (`--eupeace-blue`, `--eupeace-yellow`).

### Security Requirements
Because this application acts as a federated Identity Gateway:
* **No Hardcoded Secrets:** Never commit `.env` files, passwords, private keys, or API tokens.
* **No Certificates or Keys in Git:** Never commit any certificate or key files (`*.pem`, `*.crt`, `*.key`, `*.cert`). The `certs/` directory is completely git-ignored. All cryptographic assets must be generated or mounted locally during deployment.
* **Access Control:** Any new endpoints exposing user data or administrative actions must enforce proper authentication and authorization checks (e.g., `@login_required`, role validation).
* **Cache Prevention:** Security-sensitive endpoints (login, logout, dashboard, credential management) must include the `@never_cache` decorator to mitigate back-forward cache (bfcache) vulnerabilities.
* **Audit Logging:** Any new authentication methods or authorization gatekeeping checkpoints must create appropriate `AuditLog` records.

---

## 5. Testing & Quality Assurance

All contributions must pass existing tests and include new test cases covering any added functionality.

### Running the Test Suite
Before opening a pull request, verify that all unit and integration tests pass:

* **Inside Docker:**
  ```bash
  docker compose exec web python manage.py test
  ```

* **Locally via Virtualenv:**
  ```bash
  DATABASE_URL=sqlite:////tmp/test.db python manage.py test
  ```

### Writing Tests
Add relevant test cases to `core/tests.py`:
* Validate positive scenarios (authorized access).
* Validate negative scenarios (unauthorized access, invalid credentials, affiliation mismatches).
* Check that `AuditLog` records are properly created with accurate status (`SUCCESS` / `FAILURE`).

---

## 6. Pull Request (PR) Checklist

Before submitting a Pull Request, verify:
- [ ] Your branch is up to date with the latest `main`.
- [ ] Code adheres to PEP 8 and project style conventions.
- [ ] Migrations are created and committed (if models were modified).
- [ ] All tests pass without errors (`python manage.py test`).
- [ ] New tests are included covering the changes.
- [ ] Documentation (`README.md`, `ARCHITECTURE.md`, `DEVELOPER_GUIDE.md`, or `SECURITY.md`) is updated if applicable.
- [ ] Commit messages follow the Conventional Commits format.

---

## 7. Reporting Security Issues

Please **do not** report security vulnerabilities via public GitHub issues.
Instead, consult [SECURITY.md](SECURITY.md) and report vulnerabilities directly to the security team at:
📧 **[abuse@eupeace.eu](mailto:abuse@eupeace.eu)** or **[tech@eupeace.eu](mailto:tech@eupeace.eu)**.
