from pathlib import Path


OBSOLETE_WORKFLOWS = (
    Path(".github/workflows/materialize-production-resilience.yml"),
    Path(".github/workflows/diagnose-pr-tests.yml"),
    Path(".github/workflows/materialize-collapsible-ingredients.yml"),
    Path(".github/workflows/materialize-brand-free-food-names.yml"),
    Path(".github/workflows/materialize-saved-inventory-expander.yml"),
    Path(".github/workflows/materialize-saved-inventory-expander-main.yml"),
    Path(".github/workflows/materialize-saved-inventory-expander-final.yml"),
)


def test_one_time_diagnostic_workflows_are_not_tracked():
    """Prevent temporary migration workflows from sending future failure emails."""
    for workflow in OBSOLETE_WORKFLOWS:
        assert not workflow.exists(), f"Temporary workflow must not be tracked: {workflow}"
