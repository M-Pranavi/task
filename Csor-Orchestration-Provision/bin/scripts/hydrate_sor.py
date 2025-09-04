import os
import json
import logging
import boto3
import requests
import json
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SET_PROVISION_FOUNDATION_MUTATION = """
    mutation (
        $terraform_state_file_bucket:String!,
        $deployer_terraform_plan_bucket:String!,
        $base_deployer_arn:String!, 
        $stackset_deployer_arn:String!,
        $eks_deployer_arn:String!,
        $kap_deployer_arn:String!,
        $provision_stackset_name:String!
    ) {
        setProvisionFoundation(
            provision: {
                terraformStateFileBucket:$terraform_state_file_bucket
                terraformPlanBucket:$deployer_terraform_plan_bucket
                deployerArns: {
                    baseDeployerArn:$base_deployer_arn
                    stacksetDeployerArn:$stackset_deployer_arn
                    eksDeployerArn:$eks_deployer_arn
                    kapDeployerArn:$kap_deployer_arn
                }
                stackset:{
                    name:$provision_stackset_name
                }
            }
        ) {
            csor {
                provision {
                    terraformStateFileBucket
                    terraformPlanBucket
                    deployerArns {
                        baseDeployerArn
                        stacksetDeployerArn
                        eksDeployerArn
                        kapDeployerArn
                    }
                    stackset {
                        name
                    }
                }
            }
        }
    }
"""

PROVISION_OUTPUT_FIELDS = [
    "base_deployer_arn",
    "terraform_state_file_bucket",
    "deployer_terraform_plan_bucket",
    "eks_deployer_arn",
    "kap_deployer_arn",
    "provision_stackset_name",
    "stackset_deployer_arn"
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
    response = sts_client.assume_role(RoleArn=role, RoleSessionName="provision_sor_hydration")
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
    try:
        resp_json = resp.json()
    except Exception as exception:
        logging.error("Error parsing the JSON of the GraphQL response: %s", str(exception))
        raise

    if 'errors' in resp_json:
        logging.error("GraphQL error(s) reported: %s", json.dumps(resp_json['errors'], indent=2))
        raise Exception(f"GraphQL error(s) reported: {resp_json['errors']}")
    return resp

def read_terraform_output(file_path):
    """Read terraform_outputs.json and map required outputs."""
    try:
        with open(file_path, encoding='utf-8') as file:
            data = json.load(file)
        outputs = {key: data[key]['value'] if key in data else None
                   for key in list(set(PROVISION_OUTPUT_FIELDS))}
        logging.info("Terraform outputs mapped: %s", outputs)
        return outputs
    except Exception as err:
        logging.error("Error reading terraform_outputs.json: %s", err)
        return {}

def call_set_provision_foundation(environment_json, outputs):
    """Prepare and call setProvisionFoundation mutation."""
    for k, v in outputs.items():
        if v is None:
            logging.error(f"The required field ‘{k}’ is missing or null in terraform_outputs.json!")
            raise Exception(f"The required field ‘{k}’ is missing or null in terraform_outputs.json!")
    data = {
        "query": SET_PROVISION_FOUNDATION_MUTATION,
        "variables": outputs
    }
    resp = send_graphql_mutation(environment_json, data)
    logging.info("GraphQL setProvisionFoundation response: %s", resp.text)
    return resp

def main():
    try:
        environment_json = read_env_config()
        outputs = read_terraform_output("terraform_outputs.json")
        if not any(outputs.values()):
            logging.warning("No outputs to send.")
            return
        call_set_provision_foundation(environment_json, outputs)
        logging.info("Script completed successfully.")
    except Exception as err:
        logging.error("Unexpected error: %s", err)
        raise

if __name__ == "__main__":
    main()
