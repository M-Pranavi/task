import os
import json
import logging
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SET_BASELINE_FOUNDATION_MUTATION = """
    mutation (
        $orchestrationAccountId: String!,
        $region: Region!,
        $environment: CsorEnvironment!,
        $vpcId: String!,
        $privateSubnets: [String!]!,
        $publicSubnets: [String!]!,
        $terraformStateKey: String!,
        $terraformDynamodbLockTable: String!,
        $dynamodbGlobalDeployerLockTable: String!,
        $terraformStateFileBucket: String!,
        $terraformPlanBucket: String!,
        $baseDeployerArn: String!,
        $stacksetDeployerArn: String!,
        $loggingDeployerArn: String!,
        $networkDeployerArn: String!,
        $securityShieldDeployerArn: String!,
        $cicdDeployerArn: String!,
        $name: String!
    ) {
        setBaselineFoundation(
            orchestrationAccountId: $orchestrationAccountId, 
            region: $region, 
            environment: $environment, 
            vpcId: $vpcId, 
            privateSubnets: $privateSubnets, 
            publicSubnets: $publicSubnets, 
            terraformStateKey: $terraformStateKey, 
            terraformDynamodbLockTable: $terraformDynamodbLockTable, 
            dynamodbGlobalDeployerLockTable: $dynamodbGlobalDeployerLockTable, 
            baseline: { 
                terraformStateFileBucket: $terraformStateFileBucket,
                terraformPlanBucket: $terraformPlanBucket,
                deployerArns: {
                    baseDeployerArn: $baseDeployerArn,
                    stacksetDeployerArn: $stacksetDeployerArn,
                    loggingDeployerArn: $loggingDeployerArn,
                    networkDeployerArn: $networkDeployerArn,
                    securityShieldDeployerArn: $securityShieldDeployerArn,
                    cicdDeployerArn: $cicdDeployerArn
                }, 
                stackset: {
                    name: $name
                }
            }
        ) {
            csor {
                orchestrationAccountId
                region
                environment
                vpcId
                privateSubnets
                terraformStateKey
                terraformDynamodbLockTable
                dynamodbGlobalDeployerLockTable
                baseline {
                    terraformStateFileBucket
                    terraformPlanBucket
                    deployerArns {
                        baseDeployerArn
                        stacksetDeployerArn
                        loggingDeployerArn
                        networkDeployerArn
                        securityShieldDeployerArn
                        cicdDeployerArn
                    }
                    stackset {
                        name
                    }
                }
            }
        }
    }
"""

SET_BRAINTREE_FOUNDATION_MUTATION = """
    mutation (
        $accountId: String!,
        $cpairAssumeRole: String!,
        $environment: Environment!
    ) {
        setBraintreeFoundation(
            cosmos: {
                accountId: $accountId,
                cpairAssumeRole: $cpairAssumeRole,
                environment: $environment
            }
        ) {
            braintree {
                cosmos {
                    accountId
                    environment
                    cpairAssumeRole
                }
            }
        }
    }
"""

BASELINE_OUTPUT_FIELDS = [
    "orchestration_account_id",
    "orchestration_region",
    "csor_environment",
    "orchestration_vpc_id",
    "orchestration_vpc_private_subnets",
    "orchestration_vpc_public_subnets",
    "terraform_state_key",
    "dynamodb_state_file_lock_table_id",
    "deployer_global_lock_table",
    "tenant_state_file_bucket",
    "deployer_terraform_plan_bucket",
    "baseline_base_deployer_arn",
    "baseline_stackset_deployer_arn",
    "baseline_logging_deployer_arn",
    "baseline_network_deployer_arn",
    "baseline_security_shield_deployer_arn",
    "baseline_cicd_deployer_arn",
    "baseline_stackset_name"
]

BRAINTREE_OUTPUT_FIELDS = [
    "cosmos_account_id_mapping_to_csor",
    "cosmos_cpair_assume_role_for_cosmos_account",
    "cosmos_environment_mapping_to_csor"
]

def read_env_config():
    """Read environment configuration file defined by ENVIRONMENT_JSON."""
    env_json_path = os.getenv('ENVIRONMENT_JSON')
    if not env_json_path:
        logging.error('ENVIRONMENT_JSON environment variable not found.')
        raise Exception('ENVIRONMENT_JSON environment variable not found.')
    if not os.path.exists(env_json_path):
        logging.error(f'ENVIRONMENT_JSON file not found at {env_json_path}')
        raise Exception(f'ENVIRONMENT_JSON file not found at {env_json_path}')
    with open(env_json_path) as json_file:
        environment_json = json.load(json_file)
    for field in ('sor_url', 'orchestration_aws_assume_role', 'sor_aws_region'):
        if field not in environment_json:
            logging.error(f'Required field {field} missing in ENVIRONMENT_JSON.')
            raise Exception(f'Required field {field} missing in ENVIRONMENT_JSON.')
    return environment_json

def make_request(method, url, data, role, region):
    """Make a HTTP request to the SOR using specified role and region credentials."""
    awsrequest = AWSRequest(
        method=method,
        url=url,
        data=json.dumps(data),
    )
    sts_client = boto3.client('sts')
    response = sts_client.assume_role(RoleArn=role, RoleSessionName="sor_hydrate_session")
    session = boto3.Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken'],
        region_name=region
    )
    SigV4Auth(session.get_credentials(), 'execute-api', session.region_name).add_auth(awsrequest)
    headers = dict(awsrequest.headers)
    resp = requests.request(
        method=method,
        url=url,
        data=json.dumps(data),
        headers=headers,
        verify=False,
        timeout=10
    )
    if resp.status_code != 200:
        raise Exception(f"Request failed with status code {resp.status_code}. Response: {resp.text}")
    return resp

def send_graphql_mutation(environment_json, data):
    """Send a mutation request to SOR."""
    logging.info("GraphQL mutation being sent: %s", json.dumps(data, indent=2))
    resp = make_request(
        method="POST",
        url=environment_json['sor_url'],
        data=data,
        role=environment_json['orchestration_aws_assume_role'],
        region=environment_json['sor_aws_region'],
    )
    return resp

def read_terraform_output(file_path):
    """Read terraform_outputs.json and map required outputs."""
    try:
        with open(file_path, encoding='utf-8') as file:
            data = json.load(file)
        outputs = {key: data[key]['value'] if key in data else None
                   for key in list(set(BASELINE_OUTPUT_FIELDS + BRAINTREE_OUTPUT_FIELDS))}
        logging.info("Terraform outputs mapped: %s", outputs)
        return outputs
    except Exception as err:
        logging.error("Error reading terraform_outputs.json: %s", err)
        return {}

def call_set_baseline_foundation(environment_json, outputs):
    """Prepare and call setBaselineFoundation mutation."""
    variables = {
        "orchestrationAccountId": outputs.get("orchestration_account_id"),
        "region": outputs.get("orchestration_region"),
        "environment": outputs.get("csor_environment"),
        "vpcId": outputs.get("orchestration_vpc_id"),
        "privateSubnets": outputs.get("orchestration_vpc_private_subnets") if isinstance(outputs.get("orchestration_vpc_private_subnets"), list) else [outputs.get("orchestration_vpc_private_subnets")],
        "publicSubnets": outputs.get("orchestration_vpc_public_subnets") if isinstance(outputs.get("orchestration_vpc_public_subnets"), list) else [outputs.get("orchestration_vpc_public_subnets")],
        "terraformStateKey": outputs.get("terraform_state_key"),
        "terraformDynamodbLockTable": outputs.get("dynamodb_state_file_lock_table_id"),
        "dynamodbGlobalDeployerLockTable": outputs.get("deployer_global_lock_table"),
        "terraformStateFileBucket": outputs.get("tenant_state_file_bucket"),
        "terraformPlanBucket": outputs.get("deployer_terraform_plan_bucket"),
        "baseDeployerArn": outputs.get("baseline_base_deployer_arn"),
        "stacksetDeployerArn": outputs.get("baseline_stackset_deployer_arn"),
        "loggingDeployerArn": outputs.get("baseline_logging_deployer_arn"),
        "networkDeployerArn": outputs.get("baseline_network_deployer_arn"),
        "securityShieldDeployerArn": outputs.get("baseline_security_shield_deployer_arn"),
        "cicdDeployerArn": outputs.get("baseline_cicd_deployer_arn"),
        "name": outputs.get("baseline_stackset_name"),
    }
    for k, v in variables.items():
        if v is None:
            logging.error(f"The required field ‘{k}’ is missing or null in terraform_outputs.json!")
            raise Exception(f"The required field ‘{k}’ is missing or null in terraform_outputs.json!")
    data = {
        "query": SET_BASELINE_FOUNDATION_MUTATION,
        "variables": variables
    }
    resp = send_graphql_mutation(environment_json, data)
    logging.info("GraphQL setBaselineFoundation response: %s", resp.text)
    return resp

def call_set_braintree_foundation(environment_json, outputs):
    """Prepare and call setBraintreeFoundation mutation."""
    cosmos_env = outputs.get("cosmos_environment_mapping_to_csor")
    variables = {
        "accountId": outputs.get("cosmos_account_id_mapping_to_csor"),
        "cpairAssumeRole": outputs.get("cosmos_cpair_assume_role_for_cosmos_account"),
        "environment": cosmos_env.upper() if cosmos_env else cosmos_env,
    }
    for k, v in variables.items():
        if v is None:
            logging.error(f"The required field ‘{k}’ is missing or null in terraform_outputs.json!!")
            raise Exception(f"The required field ‘{k}’ is missing or null in terraform_outputs.json!")
    data = {
        "query": SET_BRAINTREE_FOUNDATION_MUTATION,
        "variables": variables
    }
    resp = send_graphql_mutation(environment_json, data)
    logging.info("GraphQL setBraintreeFoundation response: %s", resp.text)
    return resp

def main():
    try:
        environment_json = read_env_config()
        outputs = read_terraform_output("terraform_outputs.json")
        if not any(outputs.values()):
            logging.warning("No outputs to send.")
            return
        call_set_baseline_foundation(environment_json, outputs)
        call_set_braintree_foundation(environment_json, outputs)
        logging.info("Script completed successfully.")
    except Exception as err:
        logging.error("Unexpected error: %s", err)
        raise

if __name__ == "__main__":
    main()
