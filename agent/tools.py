def deployment_allowed(
    explicit_approval: bool,
    tests_passed: bool,
) -> bool:
    """
    Deployment requires both explicit user approval
    and successful tests.
    """
    return explicit_approval and tests_passed
