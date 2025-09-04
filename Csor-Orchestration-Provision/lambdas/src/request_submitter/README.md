# Request-Submitter

## Lambda Documentation

### Application Code

Application code is an AWS Lambda that is writen using python 3.10. It is configurable through the use of environmental variables.

#### List of Application Environmental Variables

- DYNAMODB_TABLE: string
  - Default value: testing
- STATE_MACHINE_ARN: string
  - Default value: testing
- RETRY_LIMIT: string
  - Default Value: 10
- REGION: string
  - default Value: us-east-1
- LOG_LEVEL: string
  - Default Value: DEBUG
- STACKTRACE_LIMIT: string
  - Default Value: 10

#### List of Application Global Variables

- DATA_MODEL: dictionary

#### List of Application Functions

- create_table_interface

  Creates a resource interface to a DynamoDB table.
  Returns the resource interface.

- get_item_from_table

  Get an item from a provided DynamoDB table based on a supplied key.
  Returns the retrieved item.

- put_item_in_table

  Puts an item into a provided DynamoDB table.
  Returns the response from DynamoDb.

- start_state_machine

  Starts a state machine based on a supplied ARN.
  Returns metadata about the started state machine.

- backoff_timing

  Using a supplied integer, it will return that integer raised to a power of 
  itself.

- configure_logging

  Creates a root logging singleton and sets the traceback limit for the
  application based on the log level. If the log level is DEBUG then
  traceback is enabled. If not, it is disabled.

- convert_submitted_bom_for_state_machine_use

  Takes a bill of materials that is in a dictionary format and returns
  it's string-ified form.

- verify_credentials

  Uses a call to STS to get the caller identity to confirm that AWS 
  credentials are provided for the lambda through some form. Returns
  a dictionary of the identity that STS responds with.

- lambda_handler

  This is the main program execution loop. It returns the result of the
  `put_item_in_table` function if that function was successful.

### Unit Tests

Tests are writen using the third-party Python libraries `moto` and `pytest`. The tests are housed in the tests directory.

#### List of Setup Functions in the Unit Tests

- create_populated_dynamodb_table
- create_unpopulated_dynamodb_table
- create_testing_state_machine
- set_aws_test_credentials

#### List of Tests in the Unit Tests

- test_credentials_present_returns_identity_dictionary
- test_create_dynamodb_resource
- test_getting_known_item_from_table
- test_getting_missing_item_from_table
- test_putting_item_into_table
- test_start_state_machine_successfully
- test_backoff_timing_for_zero_retries
- test_backoff_timing_for_one_retry
- test_backoff_timing_for_two_retries
- test_backoff_timing_for_three_retries
- test_traceback_limit_is_10_by_default_with_debug_logging
- test_traceback_limit_is_configurable_to_5_with_debug_logging
- test_traceback_limit_is_zero_when_using_info_logging
- test_default_logging_level_is_debug
- test_logging_level_is_configurable_to_info
- test_bom_conversion_to_string

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
| <a name="input_stepfunction"></a> [stepfunction](#input\_stepfunction) | Step Function for orchestration | `string` | n/a | yes |
| <a name="input_subnets"></a> [subnets](#input\_subnets) | Subnets for run Lambda | `list(string)` | n/a | yes |
| <a name="input_targetgroupalb"></a> [targetgroupalb](#input\_targetgroupalb) | Target Group for ALB | `string` | n/a | yes |

### Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambdaRequestSubmitterARN"></a> [lambdaRequestSubmitterARN](#output\_lambdaRequestSubmitterARN) | n/a |
