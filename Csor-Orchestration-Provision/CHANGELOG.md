# CSoR Orchestration Provision Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to Timestamp Versioning.

## [Unreleased]
- Add dependency review workflow

## [0.3.0](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.2.5...0.3.0)
- Adding generic framework testing state machine in parallel to existing braintree state machine in internal-dev.
- Hydrate SOR using Jenkins credentials temporarily
- Add btDeploy for Terraform Jenkins stages in non-prod environments
- Enabling timestamps in the Jenkins pipeline logs
- Updating the release.sh script for propogating the changes for auto-update

## [0.2.5](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.2.4...0.2.5)
- Update base deployer version to 0.1.13 across all environments
- Adding S3 deploy functionality in Jenkins pipelines

## [0.2.4](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.2.3...0.2.4)
- Stackset and provision base deployer version updates

## [0.2.3](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.2.2...0.2.3)
- Remove references the use of the serverless framework for python packaging
- Pass cosmos account number to base deployer for eks role trust relationship

## [0.2.2](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.2.1...0.2.2)
- Pin provider and module version

## [0.2.1](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.2.0...0.2.1)
- Updated eks deployer to [0.5.0](https://github.com/PayPal-Braintree/csor-eks-deployer/releases/tag/0.5.0)

## [0.2.0](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.1.1...0.2.0)
- Generate Crowdstrike Falcon Container Definitions via Jenkins and store/retrieve to/from S3

## [0.1.1](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/0.1.0...0.1.1)
- Updated release script to use semantic versioning (semver) instead of timestamp-based version tags
- Add Crowdstrike Falcon Container Sensor to ECS cluster
- Container definitions S3 bucket
- Temporarily revert ECS task definition for release

## [0.1.0](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-06-26T1653...0.1.0)
- Updated release script to use semantic versioning (semver) instead of timestamp-based version tags
- Pinning the version for ECS module to ~ 5.12.1

## [2025-06-26T1653](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-06-24T2305...2025-06-26T1653)
- Bump stackset, base, eks and kap deployer version, and remove unused S3 deployer

## [2025-06-24T2305](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-05-29T1934...2025-06-24T2305)
- Creating CHANGELOG file and and mandatory check to ensure it is updated during PR build 
- Documenting bt-authorize instructions in release section
- Hydrate CSoR Foundation data from Provision Repository to SOR

## [2025-05-29T1934](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-05-14T1310...2025-05-29T1934)
- Terraform Version 1.11.3 for base deployer and eks deployer

## [2025-05-14T1310](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-05-02T1421...2025-05-14T1310)
- Update Terraform Version to 1.11.3
- Intermittent Jenkins build usage 

## [2025-04-28T1622](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-04-17T2147...2025-04-28T1622)
- Use deployer scripts version 0.2.2 in deployers

## [2025-04-17T1900](https://github.com/PayPal-Braintree/csor-orchestration-provision/compare/2025-04-08T2356...2025-04-17T1900)
- graphql: Use accounts query
- Add CodeQLv2
