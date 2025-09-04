# csor-orchestration-baseline

## Table of Contents
- [Description](#description)
- [Requirements](#requirements)
- [Usage](#usage)
- [New Environment](#new-environment)
- [Deploying](#deploying)
- [Release Process](#release-process)
- [Pipeline Steps](#pipeline-steps)
- [Scripts](#scripts)
- [Contributing](#contributing)
- [General Guidelines](#general-guidelines)
- [Contact](#contact)
---

### Description
This is the orchestration account in CSoR system. This repo has:
- the state machine that executes all deployers, and
- the orchestration database

This repository contains the following components:
| Directory | Description |
| --- | --- |
| `bin/` | Script to release this repository as well as scripts to package and upload lambdas to S3.
| `environments/` | json files which has the parameters defined for all the environments.
| `infrastructure/` | All IaC code (terraform). |
| `lambdas/` | Lambda code (Python) |

The deploy is managed by Jenkins in the file [`Jenkinsfile`](https://github.com/PayPal-Braintree/csor-orchestration-baseline/blob/main/Jenkinsfile).
- **PR** Request in this repo will trigger a pipeline run to TF Checks and TF Plan in the **Dev environment**, 
- **PR** Merge in this repo will trigger a pipeline run to TF Apply in the **Dev environment**.
- To apply changes to the higher environments, refer to the **Release** section.
- CHANGELOG update is checked during PR build

### Requirements
*<Add here the requirements>*
*use the example below and replace according your repository* 

- Teraform >= 1.5.2
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

### Usage

Jenkins pipeline is using a Docker image created in the dockerfiles repository called [csor-tooling](https://github.com/PayPal-Braintree/dockerfiles/blob/main/app_base/csor_tooling/). The image is passed as an environment variable in the Jenkinsfile

The deployment is done by Jenkins and it is using an AWS Credential provided by CCOE Service Account **(CSOR_<ENV>_ORCHESTRATION)**, this account has a IAM User and it's AWS Access Key and Secret is configured as a credential in the pipeline configuration. This service account also has a role created in the AWS security foundation account, the role is used by terraform init (backend).

The role is configure in [terraform.tf]()

```
provider "aws" {
  assume_role {
    role_arn = "arn:aws:iam::614751254790:role/csor-nonprod-dev-jenkins-service-account-role"
  }
  ...
}
```

The state is remote, using S3 to save the state file, in this case using the same role.
```
terraform {
  ...
  backend "s3" {
    # State path will be /workspace_key_prefix/workspace_name/key
    bucket = "csor-nonprod-terraform-state"
    key    = "sor-state-machine-foundation/terraform.tfstate"

    # The region the cosmos-tfstates-{account} bucket lives in
    region   = "us-east-1"
    role_arn = "arn:aws:iam::614751254790:role/csor-nonprod-dev-jenkins-service-account-role"
  }
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

### New Environment

For configuring a new environment or deployment. Follow these steps using the branch **main**:

1. Create a file in **tfvars** directory according the environment or change the *dev.tfvars* file.

    In this file, include the VPC ID that you want to use to deploy this solution.

2. For initial configuration, execute in the root directory.
```
terraform init
```

3. Plan a new deployment in the account.
```
terraform plan --var-file="tfvars/dev.tfvars
```

4. Apply all configurations in the new account.
```
terraform apply
```

6. Pipeline steps

### Deploying

#### Release Process

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

#### Foundation Configuration Document (FCD)

Current FCD:
```
{
  "account": "<aws_account_number>",
  "name": "<aws_account_name>",
  "environment": "<environment>",
  "base_deployer": "<stable-fcd-version>",
  "cicd_deployer": "<stable-fcd-version>",
  "network_deployer": "<stable-fcd-version>",
  "logging_deployer": "<stable-fcd-version>",
  "security_shield_deployer": "<stable-fcd-version>",
  "stackset_deployer": "<stable-fcd-version>"
}
```

The `stable-fcd-version` for each deployer can be found here - https://github.com/PayPal-Braintree/csor-fcd/blob/main/fcd.json

#### Pipeline steps
1. **manage build agent**

    Build the docker image to run the Terraform commands.
2. **manage test agent**

    Build the docker image for making unit tests using Pytest in the Lambdas.
3. **Run Unit Tests**

    Execute the unit tests in Lambdas.

4. **Run Terraform Scans**

    Runs the [TFLint](https://github.com/terraform-linters/tflint) and [TFSec](https://github.com/aquasecurity/tfsec).
    
    Warnings will appear in the pipeline output, the pipeline won't break when warnings are detected.


4. **[dev] terraform plan**

    Runs the *terraform fmt* for verify formatting, validate to verify some problem in files, and terraform plan. 
5. **[dev] terraform apply**

    Apply the terraform in the AWS Account.

### Scripts

#### Deployer Average Runtime

To get the average runtime of a deployer over the last 50 step function executions, run the python script `scripts/deployer_average_runtime.py`. It takes 3 arguments: `env`, `step-function-name` and `task-name`

Example - average runtime for `Base Deployer` over the last 50 executions of the `csor-orchestration-baseline` step function:
```
python bin/scripts/deployer_average_runtime.py --env internal-dev --step-function csor-orchestration-baseline --task "Base Deployer"
Average runtime of task 'Base Deployer' in 'internal-dev' environment over last 50 executions: 2.10 minutes
```

### Contributing

To contribute in this repository, ensure you have access to it. Open a Pull Request with your proposed changes, this PR will be reviewed by the bt-cloud-infra.

Also ensure that you open you PR following the bellow:

- [Development Standards](https://engineering.paypalcorp.com/confluence/display/Braintree/Simple+Development+Standards) 

### General Guidelines

- Ensure that you are familiar with the project's objective and architecture before making significant changes.
- Maintain a consistent coding style and follow the conventions adopted by the team.

### Contact

<bt-cloud-infra@paypal.com>
