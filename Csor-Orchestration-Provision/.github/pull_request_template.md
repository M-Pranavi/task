name: Security

on:
  pull_request:
    branches: [ main ]
  workflow_dispatch:

jobs:
  dependency-review:
    uses: PayPal-Braintree/security-workflows/.github/workflows/dependency-review.yml@main
