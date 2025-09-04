# Execution-Reporter

## Lambda Documentation

### Application Code

Application code is an AWS Lambda that is writen using python 3.11. It is configurable through the use of environmental variables.

#### List of Application Environmental Variables

- DYNAMODB_TABLE: string
  - Default value: N/A

#### List of Application Functions

- get_tenant_account

  Retrieves tenant account for a given state machine execution

- update_execution_status

  Updates DynamoDB with overall execution status

- hydrate_sor

  Sends a message to an SQS queue to hydrate SoR with contents from DynamoDB

- configure_logging

  Creates a root logging singleton and sets the traceback limit for the
  application based on the log level. If the log level is DEBUG then
  traceback is enabled. If not, it is disabled.

### Unit Tests

Tests are writen using the third-party Python libraries `moto` and `pytest`. The tests are housed in the tests directory.

#### List of Setup Functions in the Unit Tests

TODO

#### List of Tests in the Unit Tests

TODO

## Terraform Documentation

### Requirements

No requirements.

### Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | n/a |
| <a name="provider_aws"></a> [aws](#provider\_aws) | n/a |

### Modules

No modules.

### Resources

| Name | Type |
|------|------|
| [aws_iam_policy.request-submitter](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role.request-submitter](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.request-submitter](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.request-submitter-vpc](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_lambda_function.request-submitter](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_permission.alb_invoke_permission](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [archive_file.request-submitter](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |

### Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_orchestration_database_arn"></a> [orchestration\_database\_arn](#input\_orchestration\_database\_arn) | Database ARN to save information about the execution | `string` | n/a | yes |
| <a name="input_orchestration_database_id"></a> [orchestration\_database\_id](#input\_orchestration\_database\_id) | Database ID (name) to save information about the execution | `string` | n/a | yes |
| <a name="input_securitygroup"></a> [securitygroup](#input\_securitygroup) | SG for VPC configuration for this lambda | `string` | n/a | yes |
| <a name="input_subnets"></a> [subnets](#input\_subnets) | Subnets for run Lambda | `list(string)` | n/a | yes |
| <a name="input_eventbridge_rule_arn"></a> [eventbridge_rule_arn](#input\_eventbridge_rule_arn) | EventBridge rule ARN that invokes this function | `string` | n/a | yes |

### Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambdaExecutionReporterARN"></a> [lambdaExecutionReporterARN](#output\_lambdaExecutionReporterARN) | n/a |
| <a name="output_lambdaExecutionReporterName"></a> [lambdaExecutionReporterName](#output\_lambdaExecutionReporterName) | n/a |
