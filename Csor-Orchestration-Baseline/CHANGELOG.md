# CSoR Orchestration Baseline Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to Timestamp Versioning.

## [Unreleased]
- Add dependency review GH action
- Add KMS decrypt permissions for deployer artifact bucket
- Updating the release.sh script for propogating the changes for auto-update
- Fix kms permissions for deployer artifact bucket in orchestration accounts

## [0.3.6](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.3.5...0.3.6)
- Fix tenant-dev tfvars to contain all orchestration accounts for deployer artifacts bucket

## [0.3.5](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.3.4...0.3.5)
- Add btDeploy for Terraform Jenkins stages in non-prod environments
- Move deployer artifact bucket to tenant-dev
- Enabling timestamps in the Jenkins pipeline logs

## [0.3.4](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.3.3...0.3.4)
- Replace IAM role assume_scoped_role_root on KMS Policy.
- Adding CICD Deployer to Chargehoung State Machine. 

## [0.3.3](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.3.1...0.3.3)
- Adding S3 deploy functionality in Jenkins pipelines

## [0.3.2](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.3.1...0.3.2)
- Remove references to the use of the serverless framework for python packaging
- Refactor network hydrate lambda code to use standard csor lambda module
- Fix network hydrate lambda entrypoint
- Differentiating lambdas based on the environment for monitor alerts
- Migrating logging deployer to generic deployer framework

## [0.3.1](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.3.0...0.3.1)
- Delete AWS network firewall
- Pinning the version for ECS module to ~ 5.12.1

## [0.3.0](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.2.1...0.3.0)
- Remove firewall rules from route table
- Allowlist crowdstrike domains in network firewall
- Reuse GraphQL request session in E2E test

## [0.2.1](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.2.0...0.2.1)
- Fix Task definition creator lambda to fetch latest task definition and not update falcon ECS container image

## [0.2.0](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.1.5...0.2.0)
- Generate Crowdstrike Falcon Container Definitions via Jenkins and store/retrieve to/from S3
- Pinning version for providers and modules

## [0.1.5](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.1.4...0.1.5)
- Fix code difference link in SNOW ticket
- Container definitions S3 bucket
- Migrating Security shield deployer to generic deployer framework

## [0.1.4](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.1.3...0.1.4)
- New regions for Apollo: ap-south-2 and me-central-1

## [0.1.3](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.1.2...0.1.3)
- Fixing Datadog dashboard for security shield deployer message
- Updated for permadiff changes
- Remove CICD deployer from Apollo baseline state machine
- Add the stackset deployer to the framework state machine
- New regions for Apollo: ap-south-1 and ap-southeast-1

## [0.1.2](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.1.1...0.1.2)
- Pinning the version for ECS module to ~ 5.12.1
- Fixing Datadog dashboard for security shield message

## [0.1.1](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/0.1.0...0.1.1)
- Creating monitors and dashboard in datadog for security shield deployer functions

## [0.1.0](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/2025-06-17T1742...0.1.0)
- Updated release script to use semantic versioning (semver) instead of timestamp-based version tags

## [2025-06-17T1742](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/2025-06-17T1315...2025-06-17T1742)
- Fixes for generic deployer framework state machine and task definitions
- Adding generic framework testing state machine in parallel to existing braintree state machine in internal-dev.
- Creating CHANGELOG File and and mandatory check to ensure it is updated during PR build
- Documenting bt-authorize instructions in release section
- Fixing Terraform plan permadiff
- Hydrate CSoR Foundation Data from Baseline repository to SOR

## [2025-05-07T1916](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/2025-05-02T1812...2025-05-07T1916) 
- Update Terraform Version to 1.11.3

## [2025-05-02T1812](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/2025-04-22T2214...2025-05-02T1812) 
- Intermittent Jenkins build usage
- Create deployer artifact bucket in internal-dev
- Getting rid of this env.STABLE_FCD

## [2025-04-22T2214](https://github.com/PayPal-Braintree/csor-orchestration-baseline/compare/2025-04-09T2135...2025-04-22T2214) 
- fix: Region filter is not a string type
- graphql: Use accounts query
