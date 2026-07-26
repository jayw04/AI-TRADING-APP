"""AWS adapters for the forward-validation witness boundary (ADR 0046).

This package is the ONLY place in the backend permitted to import the AWS SDK.
`scripts/check_aws_sdk_isolation.sh` enforces that as a CI invariant, in both directions: nothing
outside this package imports `boto3`/`botocore`/`aiobotocore`/`types_boto3*`/`mypy_boto3*`, and nothing
outside this package imports `app.validation.aws` — the modules here are reached only through the
`witness.signer.factory` / `witness.sink.factory` strings in the governed deployment configuration,
resolved by `witness_enforcement._resolve_factory`.

Deliberately empty of imports. Re-exporting the adapters here would create an import edge that pulls
the SDK in whenever anything touches `app.validation.aws`, which is exactly the reachability the
invariant exists to prevent.
"""
