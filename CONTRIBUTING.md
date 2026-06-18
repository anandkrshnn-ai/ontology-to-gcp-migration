# Contributing to the Palantir to GCP Migration Toolkit

We welcome contributions to harden and extend this migration toolkit! Because this framework targets enterprise data platform architectures, all contributions must adhere to strict engineering hygiene.

## Engineering Standards

1. **No Hardcoded Credentials**: Never commit API keys, service account JSONs, or raw bearer tokens. Use Workload Identity Federation or GCP Secret Manager.
2. **Infrastructure as Code (IaC)**: All infrastructure changes must be made via Terraform modules in `terraform/modules/`.
3. **Terraform Checks**: Run `terraform fmt` and `tflint` before opening a Pull Request.
4. **Python Hygiene**: 
   - Scripts must use `argparse` for CLI configuration (no hardcoded variables in `__main__`).
   - Use the `logging` module, not `print()`.
5. **Testing**: Python modifications must include or update `pytest` coverage in the `scripts/tests/` directory.

## Pull Request Process

1. Fork the repo and create your branch from `main` or `master`.
2. Ensure your code passes the automated CI workflow.
3. Update the `README.md` if your change affects deployment architecture.
4. Wait for code review from a core maintainer.

Thank you for contributing!
