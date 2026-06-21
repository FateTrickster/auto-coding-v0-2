"""Development CLI — commands for debugging, validation, and milestone reporting.

These are NOT part of the stable production workflow. Use `cli.py` for production.
"""

from __future__ import annotations

from pathlib import Path
import typer

app = typer.Typer(name="auto_coding_dev", help="Development and validation commands")


@app.command("acceptance-audit")
def acceptance_audit_cli(
    project_dir: str = typer.Option(..., help="Project directory"),
):
    """Run v1.0 final acceptance audit (milestone reporting, not a runtime gate)."""
    from .acceptance_auditor import audit
    r = audit(project_dir)
    passed = sum(1 for c in r["checks"] if c["passed"])
    print(f"Status: {r['status']} — {passed}/{len(r['checks'])} checks passed")
    if r["status"] == "ACCEPTED_WITH_NOTES":
        print(f"Risks: {r['risks']}")


@app.command("build-audit-sample")
def build_audit_sample_cli(
    project_dir: str = typer.Option(..., help="Project directory"),
    target_size: int = typer.Option(100, help="Target sample size"),
    seed: int = typer.Option(42, help="Random seed"),
):
    """Build stratified audit sample for human + DeepSeek validation."""
    from .audit_sample_builder import build_audit_sample
    m = build_audit_sample(project_dir, target_size=target_size, seed=seed)
    print(f"Audit sample: {m['actual_size']} units (target={m['target_size']})")
    print(f"Labels: {m['label_distribution']}")
    print(f"Disagreement: {m['disagreement_samples']}, Risk: {m['risk_samples']}")
    print(f"Template: {m['template_path']}")


@app.command("write-human-audit-instructions")
def write_human_audit_instructions_cli(
    project_dir: str = typer.Option(..., help="Project directory"),
):
    """Generate human_audit_instructions.md."""
    from .human_audit_validator import write_instructions
    p = write_instructions(project_dir)
    print(f"Instructions: {p}")


@app.command("validate-human-audit")
def validate_human_audit_cli(
    project_dir: str = typer.Option(..., help="Project directory"),
):
    """Validate human_audit_template.csv."""
    from .human_audit_validator import validate
    r = validate(project_dir)
    print(f"Status: {r['status']} (ready={r['ready_for_metrics']})")
    print(f"Labeled: {r['labeled_count']}, Uncertain: {r['uncertain_count']}, Missing: {r['missing_label_count']}")


@app.command("compute-validation-metrics")
def compute_validation_metrics_cli(
    project_dir: str = typer.Option(..., help="Project directory"),
):
    """Compute mock vs human validation metrics."""
    from .validation_metrics import compute
    r = compute(project_dir)
    if r.get("status") == "AWAITING_HUMAN_LABELS":
        print(f"Status: AWAITING_HUMAN_LABELS (labeled={r.get('labeled_count', 0)})")
    else:
        print(f"Mock vs Human: Agreement={r['mock_vs_human_agreement']:.4f}, Kappa={r['mock_vs_human_kappa']:.4f}")


if __name__ == "__main__":
    app()
