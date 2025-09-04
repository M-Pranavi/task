# csor-orchestration-provision

[![Build Status](https://ci.braintree.tools/buildStatus/icon?job=braintree%2Fcsor-orchestration-provision%2Fmain)](https://ci.braintree.tools/job/braintree/job/csor-orchestration-provision/job/main/)

*Add here a brief description of your repository*

*This repository is a template to clone from when creating new repos for CSoR project. When creating a new repository, choose the option to create the repository from a template and select the repo, so all the code in this repo, including this readme.md will be cloned. The repository config as Branch Rules, Option and Access are not cloned, so you will need to configure it manually in the cloned repo*
 
***Ensure to remove all the italic text from your cloned repo, the italic texts are guidelines to use this readme from the cloned repo*** 

---

The provision API is used to deploy application specific infrastructure on demand in tenant accounts such as EKS clusters, S3 buckets, etc.

## Table of Contents

*add here your readme table of contents*

- [Description](#description)
- [Prerequisites](#requirements)
- [Usage](#usage)
- [Release Process](#release-process)
- [Contributing](#contributing)
- [Contact](#contact)

---

## Description
- *Add here a brief description of your repository, focus on add here the repository purpose, what it manages and the solution/project it is related*
- *Also add here the repository components, following the example below*

*use the example below and replace according your repository* 

This repository contains the following components:
| Directory | Description |
| --- | --- |
| `bin/` | Script to release this repository as well as scripts to package and upload lambdas to S3
| `infrastructure/` | All IaC code (terraform) |
| `lambdas/` | Lambda code (Python) |

*<add here how this code is deployed>*
*use the example below and replace according your repository* 

The deploy is managed by Jenkins [`Jenkinsfile`](https://github.com/PayPal-Braintree/csor-orchestration-provision/blob/main/Jenkinsfile).
- **PR** Request in this repo will trigger a pipeline run to TF Checks and TF Plan in the **Dev environment**, 
- **PR** Merge in this repo will trigger a pipeline run to TF Apply in the **Dev environment**.
- To apply changes to the higher environments, refer to the **Release** section.
- CHANGELOG update is checked during PR build


## Requirements
*<Add here the requirements>*
*use the example below and replace according your repository* 

- Teraform >= 1.5
- Python 3.10


### Prerequisites for Release Script

Before running the release script (`./bin/release.sh`), ensure you have the following setup:

#### 1. GitHub Personal Access Token
Create a Personal Access Token at: https://github.com/settings/tokens  
Required Scopes:
- `repo` - Full control of private repositories
- `read:org` - Read org and team membership, read org projects
- `workflow` - Update GitHub Action workflows

#### 2. GitHub CLI Authentication
The release script uses GitHub CLI to create pull requests. You must authenticate first:

```bash
gh auth login
```
Follow the prompts and select:
- GitHub.com
- HTTPS protocol
- Paste an authentication token

#### 3. Environment Variable (Optional)
You can set the token as an environment variable:
```bash
export GITHUB_TOKEN=your_personal_access_token_here
```

#### 4. Verification
Verify your authentication:
```bash
gh auth status
```

> Note: This is a one-time setup per developer workstation. Once configured, the release script will automatically handle PR creation and GitHub interactions.


## Usage
*<Add here the usage information of your repository>*
*use the example below and replace according your repository* 
  

Jenkins pipeline is using a Docker image created by another csor repository [csor-tooling](https://github.com/PayPal-Braintree/dockerfiles/blob/main/app_base/csor_tooling/). The image is passed as an environment variable in Jenkinsfile

```
pipeline {
  agent any
  environment {
    CSOR_TOOLING_IMAGE = "dockerhub.braintree.tools/bt/csor-tooling:latest"
  }
```
- [CSOR_TOOLING_IMAGE docker file](https://github.com/PayPal-Braintree/dockerfiles/blob/main/app_base/csor_tooling/Dockerfile) - This one is used for all Terraform stages in Jenkins.

The deployment is done by Jenkins and it is using an AWS Credential provided by CCOE Service Account, this account has a IAM User and it's AWS Access Key and Secret is configured as a credential in the pipeline configuration. This service account also has a role    created in the AWS security foundation account, the role is used by terraform init (backend).

The role is configure in ./infrastructure/terraform.tf
```
  backend "s3" {
    bucket = "<tfstate_bucket_name"
    key    = "<tfstate_key>.tfstate"

    region   = "<aws region>"
    role_arn = "<role_arn"
  }
```

When running a pipeline from this repo, some terraform format, code linting, security checks and error checks will be executed:
- terraform_fmt
- tflint
- tfsec
- pylint
- mypy

The TFLINT is using the .tflinh.hcl file to enable to aws linter, as follow

```
plugin "aws" {
  enabled = true
  version = "0.27.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
```

Both TFLINT and TFSEC are executed in the TFSCAN jenkins pipeline stage, warnings will appear in the pipeline output, the pipeline wont break when warnings are detected. Also both tools are installed in the CSOR_TOOLING_IMAGE docker image, that is the one used by jenkins to run the pipeline.

## Release Process
By default, changes merged to `main` are deployed to `internal-dev`. To release changes to higher environments a developer needs to tag `main` and kick off the Jenkins build.
To kick off a release to all higher environments:
```
git co main
git pull
./bin/release.sh
```
The project now uses [semantic versioning](https://semver.org/) (semver) for releases. The release script will:
1. Check for existing semantic version tags (format: X.Y.Z)
2. It will prompt you to choose the type of version increment:
   - **Major version update** (X.0.0): For backwards-incompatible changes
   - **Minor version update** (0.X.0): For backwards-compatible new features
   - **Patch update** (0.0.X): For backwards-compatible bug fixes
For more details on CSoR semantic versioning guidelines, visit our confluence page. [CSoR Versioning Guidelines](https://paypal.atlassian.net/wiki/spaces/BTSRE/pages/2266999535/CSoR+Versioning+Guidelines).
After confirming the new version, the script will tag the latest commit on `main` and kick off the Jenkins pipeline to release the changes to higher environments. As of today, this build will deploy to `internal-qa`, `dev`, `qa`, `sand` and `prod`. When the pipeline reaches the `prod` stage, a change ticket will be created automatically and an UNO notification for change ticket approval will be sent to an engineer who is online of the CloudNX team. Once the change ticket is reviewed and approved, the change ticket will automatically move to the `Implement` state. The Jenkins pipeline will then proceed and complete the production deployment, and accordingly `Close` the change ticket with a Success/Failure result.

### bt-authorize

To run bt-authorize commands, you need to have CSoR Sandbox and CSoR Production LDAP access.
- MyAccess roles - Sandbox: `PP_BT_LDAP_SAND_CSOR_ADMIN`, Production: `PP_BT_LDAP_PROD_CSOR_ADMIN`
- Sandbox and Production deploys require manual authorization using `bt-authorize`. As part of the release pipeline, Jenkins will notify in `#csor-builds` when a build stage is ready to be authorized.
- Follow the link to the Jenkins build
- Review the terraform diff
- Confirm no conflicting operations are in progress
- Run the provided `bt-authorize` command from your laptop to proceed (if you haven’t installed `bt-authorize`, follow the [installation instructions](https://github.com/PayPal-Braintree/jenkins-production-worker#installing-bt-authorize) included in the slack prompt)
- For Sandbox deploys, we use bt-authorize for terraform apply
- For Production deploys, the order of actions are bt-authorize for terraform plan -> confirm diff in pipeline via Jenkins UI -> SNOW ticket -> bt-authorize for terraform apply

After the release is complete, create a new pull request to update the CHANGELOG: move the contents of the `Unreleased` section under the newly created tag, and leave the `Unreleased` section empty. 

List of Approvers: [CloudNX](https://paypal.service-now.com/now/nav/ui/classic/params/target/sys_user_group.do%3Fsys_id%3Df81549bf9720869c901f36be2153af63%26sysparm_view%3Dtext_search) 

Associated CI: [csor_platform](https://paypal.service-now.com/cmdb_ci_sdlc_component.do?sys_id=e868b469c3ad9e14725eabec7a013109&sysparm_record_target=cmdb_ci_sdlc_component&sysparm_record_row=2&sysparm_record_rows=5&sysparm_record_list=sys_created_on%3E%3D2024-10-28+14%3A41%3A50%5Esys_created_by%3Daiswv%5EORDERBYname)

The notification of the deployment request and result will be sent to the `#csor-builds` slack channel


## Contributing

To contribute in this repository, ensure you have access to it. Open a Pull request with your proposed changes, this PR will be reviewed by the bt-cloud-infra.

Also ensure that you open you PR following the bellow:

- [Development Standards](https://engineering.paypalcorp.com/confluence/display/Braintree/Simple+Development+Standards) 
- Add the items you changed in your PR to the CHANGELOG.md file


### General Guidelines

- Ensure that you are familiar with the project's objective and architecture before making significant changes.
- Maintain a consistent coding style and follow the conventions adopted by the team.

## Contact

<bt-cloud-infra@paypal.com>
