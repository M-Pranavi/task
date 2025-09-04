"""Request Submitter lambda to start baseline state machine."""

import json
import logging
import os
import re
from typing import Dict,Tuple, Optional

import boto3
import botocore
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session

STATE_FILE_PREFIX: str = 'csor-orchestration-baseline-statefiles-'
STATE_MACHINE_ARNS: dict = json.loads(os.getenv('STATE_MACHINE_ARNS', "{}"))
ORCHESTRATION_REGION: str = str(os.getenv('ORCHESTRATION_REGION', 'us-east-2')).lower()
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

DEPLOYERS_PER_BU: dict = {
    "Apollo": [
        "base_deployer",
        "stackset_deployer",
        "security_shield_deployer",
        "cicd_deployer",
        "logging_deployer",
    ],
    "Braintree": [
        "base_deployer",
        "stackset_deployer",
        "security_shield_deployer",
        "cicd_deployer",
        "logging_deployer",
        "network_deployer",
    ],
    "Chargehound": [
        "base_deployer",
        "stackset_deployer",
        "security_shield_deployer",
    ],
    # TODO: Remove after framework cutover. Used for routing in testing
    "Framework": [
        "stackset_deployer",
        "base_deployer",
        "security_shield_deployer",
        "logging_deployer",
    ]
}

TRUST_POLICY: dict = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "s3.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}

CREATE_EXECUTION_MUTATION = """
    mutation ($executionArn: String!, $accountId: String!, $type: StateMachine!, $status: OrchestrationStatus!, $startTime: ISO8601DateTime!,
        $deployers: [DeployerInput!]!, $configurationDocument: JSON!, $region: Region!){
      createStateMachineExecution(accountId: $accountId, executionArn: $executionArn, type: $type, startTime: $startTime, status: $status,
        deployers: $deployers, configurationDocument: $configurationDocument, region: $region) {
        arn
        region
        status
        startTime
        deployers {
          name
          status
        }
        configurationDocument
      }
    }
"""

ACCOUNT_QUERY = """
    query ($id:String!) {
        accounts(id:$id) {
            id
            regions
            businessUnit
        }
    }
"""

ACCOUNT_EXECUTIONS = """
    query ($id: String!, $region: Region!) {
        accounts(id: $id, region: $region) {
            id
            baseline {
                region
                latest {
                    arn
                    startTime
                    status
                }
            }
        }
    }
"""

def __create_ecr_client():
    """Create a boto3 ECR client."""
    return boto3.client('ecr', region_name=ORCHESTRATION_REGION)


def sign_request(url, method, headers, body):
    """Sign the request using SigV4"""
    session = get_session()
    credentials = session.get_credentials().get_frozen_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, 'execute-api', os.getenv('ORCHESTRATION_REGION')).add_auth(request)
    return request


def invoke_api_gateway(api_url, raw_query=None):
    """Invoke API Gateway with SigV4 signing"""
    headers = {
        'Content-Type': 'application/json'
    }
    body = json.dumps(raw_query)
    signed_request = sign_request(api_url, 'POST', headers, body)
    response = requests.post(api_url, data=signed_request.body, headers=dict(signed_request.headers.items()))

    if response.status_code != requests.codes.ok:
        msg = f"Failed to communicate with {api_url}. Code: {response.status_code}, Reason: {response.reason}, Text: {response.text}"
        raise requests.exceptions.RequestException(msg)

    return response.json()


def execute_sor_query(query: str, variables: dict = None) -> dict:
    """Invoke the GraphQL query via API Gateway"""
    raw_query = {
        "query": query,
        "variables": variables or {}
    }
    
    api_url = os.getenv('SOR_ENDPOINT')
    response = invoke_api_gateway(
        api_url=api_url,
        raw_query=raw_query
    )

    if 'errors' in response:
        raise RuntimeError(f"GraphQL returned errors: {response}")

    return response


def start_state_machine(state_machine_arn: str, fcd: str, region: str):
    """Execute the target statemachine with the supplied bill of materials."""
    result: Dict[str, str] = {
        'execution_arn': 'undefined',
        'start_date': 'undefined'
    }
    try:
        client = boto3.client(
            service_name='stepfunctions',
            region_name=region)
        response = client.start_execution(input=fcd,
                                          stateMachineArn=state_machine_arn)
        result = {'execution_arn': response['executionArn'],
                  'start_date': response['startDate']}
    except botocore.exceptions.ClientError as err:
        raise err from err
    logging.debug('State machine response:\n%s', response)
    return result


def configure_logging(log_level: str = 'INFO'):
    """Configure the root logger for the lambda."""
    logging.getLogger().setLevel(log_level.upper())


def validate_deployer_versions(ecr_client, deployers, registry_id):
    """Validate that all deployer versions given exist in ECR."""
    messages = []
    for name, version in deployers.items():
        if name == "base_deployer":
            name = "baseline_base_deployer"

        try:
            response = ecr_client.describe_images(
                registryId=registry_id,
                repositoryName=name,
                imageIds=[{'imageTag': version}]
            )
        except ecr_client.exceptions.ImageNotFoundException:
            messages.append(f"Image {version} not found for {name}.")

    logging.info(f"Found {len(messages)} invalid versions in FCD.")

    return '\n'.join(message for message in messages)


def validate_fcd(event: dict, ecr_client, registry_id) -> dict:
    """Validate that the fcd submitted is valid."""
    try:
        fcd = json.loads(event['body'])
    except json.JSONDecodeError:
        raise ValueError('Invalid foundation configuration document: invalid JSON')

    deployers = {key: value for key, value in fcd.items() if "deployer" in key}

    # TODO: Remove this after framework cutover.
    # We don't need to validate versions in ECR anymore. This should be changed to S3 after cutover.
    if 'framework' in fcd and fcd['environment'] == 'DEV':
        logging.info("Skipping deployer version validation for framework in DEV environment.")
        return fcd

    message = validate_deployer_versions(ecr_client, deployers, registry_id)
    if message:
        raise ValueError(message)
    return fcd


def send_response(http_code, body, event_headers, resource_id=None):
    """Send response back to the client."""
    content_type = 'application/json'
    body = {'message': body}
    if http_code == 200:
        body['resourceId'] = resource_id
    body = json.dumps(body)

    response = {
        'statusCode': http_code,
        'isBase64Encoded': False,
        'headers': {
            'Content-Type': content_type
        },
        'body': body
    }
    logging.info(response)
    return response


def state_file_bucket(bucket_region: str, state_machine_arn: str):
    """Create a state file bucket for the account."""
    arn_splited = state_machine_arn.split(":")
    account_id = arn_splited[4]
    bucket_name = STATE_FILE_PREFIX + account_id
    s3_client = boto3.client('s3', region_name=bucket_region)
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        logging.info("Bucket already exists: %s", bucket_name)
    except s3_client.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            create_buckets(bucket_region, bucket_name)
        else:
            logging.error("Error checking bucket: %s", e)
            raise e


def create_buckets(bucket_region: str, bucket_name: str) -> None:
    s3_client = boto3.client('s3', region_name=bucket_region)
    bucket_name_replication = bucket_name + "-replica"
    try:
        s3_client.create_bucket(Bucket=bucket_name,
                                CreateBucketConfiguration={'LocationConstraint': bucket_region})
        logging.info("Created state file bucket: %s", bucket_name)
        s3_client.create_bucket(Bucket=bucket_name_replication,
                                CreateBucketConfiguration={'LocationConstraint': bucket_region})
        logging.info("Created state file bucket: %s", bucket_name_replication)
        try:
            s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={
                    'Status': 'Enabled'
                }
            )
            logging.info("Bucket versioning enabled for %s", bucket_name)
            s3_client.put_bucket_versioning(
                Bucket=bucket_name_replication,
                VersioningConfiguration={
                    'Status': 'Enabled'
                }
            )
            logging.info("Bucket versioning enabled for %s", bucket_name_replication)
            configure_replication(bucket_name, bucket_name_replication)
        except s3_client.exceptions.ClientError as e:
            logging.error("Failed to enable versioning on the bucket: %s", e)
            raise e
    except s3_client.exceptions.ClientError as e:
        logging.error("Failed to create bucket: %s", e)
        raise e


def configure_replication(bucket_name: str, bucket_name_replication: str):
    iam_client = boto3.client('iam')
    try:
        response = iam_client.create_role(
            RoleName='replication-' + bucket_name,
            AssumeRolePolicyDocument=json.dumps(TRUST_POLICY),
            Description='Role for S3 bucket replication',
        )
        role_arn = response['Role']['Arn']
        logging.info("Created role ARN: %s", role_arn)

        REPLICATION_POLICY = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": [
                        "s3:ListBucket",
                        "s3:GetReplicationConfiguration",
                        "s3:PutObjectVersionForReplication",
                        "s3:GetObjectVersionForReplication",
                        "s3:GetObjectVersionAcl",
                        "s3:GetObjectVersionTagging",
                        "s3:GetObjectRetention",
                        "s3:GetObjectLegalHold"
                    ],
                    "Effect": "Allow",
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}",
                        f"arn:aws:s3:::{bucket_name}/*",
                        f"arn:aws:s3:::{bucket_name_replication}",
                        f"arn:aws:s3:::{bucket_name_replication}/*"
                    ]
                },
                {
                    "Action": [
                        "s3:ReplicateObject",
                        "s3:ReplicateDelete",
                        "s3:ReplicateTags",
                        "s3:ObjectOwnerOverrideToBucketOwner"
                    ],
                    "Effect": "Allow",
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}/*",
                        f"arn:aws:s3:::{bucket_name_replication}/*"
                    ]
                }
            ]
        }

        logging.info("Created replication policy: %s", REPLICATION_POLICY)
        iam_client.put_role_policy(
            RoleName='replication-' + bucket_name,
            PolicyName='S3ReplicationPolicy',
            PolicyDocument=json.dumps(REPLICATION_POLICY)
        )
        logging.info("Attached the replication policy to the role from bucket %s to %s", bucket_name, bucket_name_replication)
    except Exception as e:
        logging.info("Error creating role or attaching policy: %s", e)

    try:
        s3_client = boto3.client('s3')

        replication_configuration = {
            'Role': f'{role_arn}',
            'Rules': [
                {
                    'ID': 'Replication',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'DeleteMarkerReplication': {'Status': 'Disabled'},
                    'Filter': {'Prefix': ''},
                    'Destination': {
                        'Bucket': f'arn:aws:s3:::{bucket_name_replication}',
                    },
                },
            ]
        }

        s3_client.put_bucket_replication(
            Bucket=bucket_name,
            ReplicationConfiguration=replication_configuration
        )
    except s3_client.exceptions.ClientError as e:
        logging.error("Failed to activate the replication: %s", e)
        raise e


def parse_request_info(request_context):
    """Retrieve tracking information from the incoming request context"""
    # Retrieve caller id
    user_arn = request_context['identity']['userArn']
    caller = re.findall('arn:aws:sts::[0-9]+:assumed-role/.*/(.*)', user_arn)[0]

    # Retrieve request ID assigned my apigw
    request_id = request_context['requestId']

    return {
        "user_arn" : caller,
        "request_id": request_id
    }


def get_headers(event):
    return event['headers'] if 'headers' in event else None

def check_execution_status(account_id: str, tenant_region: str) -> Tuple[bool, Optional[str]]:
    variables = {"id": account_id, "region": tenant_region}
    response = execute_sor_query(ACCOUNT_EXECUTIONS, variables)
    logging.info('SOR Response: %s', response)

    region_summaries = response['data']['accounts'][0]['baseline']
    for region_summary in region_summaries:
        latest_execution = region_summary.get('latest')
        if latest_execution:
            lastest_execution_status = latest_execution['status']
            execution_arn = latest_execution['arn']
            if lastest_execution_status == "IN_PROGRESS":
                logging.info('Account ID %s: Execution in progress with ARN %s.', account_id, execution_arn)
                return True, execution_arn
    return False, None

def lambda_handler(event: dict, context: dict) -> dict:
    """Execute lambda process."""
    configure_logging(LOG_LEVEL)

    request_info = parse_request_info(event['requestContext'])

    logging.info(
        "Received new request: ID: %s, Caller: %s",
        request_info['request_id'],
        request_info['user_arn'],
    )

    logging.debug(
        "Lambda received event: %s\n with context: %s\n",
        event,
        context,
    )

    docker_registry = os.getenv("DOCKER_REGISTRY")
    if not docker_registry:
        raise KeyError('Failed to get the DOCKER_REGISTRY environment variable')

    registry_id = docker_registry.split('.')[0]
    ecr_client = __create_ecr_client()

    try:
        fcd = validate_fcd(event, ecr_client, registry_id)
        account_info = execute_sor_query(ACCOUNT_QUERY, {"id": fcd['account']})
    except (KeyError, ValueError) as e:
        return send_response(400, str(e), get_headers(event))
    except Exception as e:
        return send_response(400, f"Encountered error when looking up account: {str(e)}", get_headers(event))

    if not account_info['data']['accounts'] or account_info['data']['accounts'][0]['id'] != fcd['account']:
        return send_response(400, "Account has not been onboarded. Please onboard it using runbook: https://paypal.atlassian.net/wiki/spaces/BTSRE/pages/939401510/Onboard+AWS+Account+to+CSoR", get_headers(event))

    tenant_regions = account_info['data']['accounts'][0]['regions']
    if fcd['region'] not in tenant_regions:
        return send_response(400, f"Requested region '{fcd['region']}' is not in list of allowed tenant regions from SOR {tenant_regions}", get_headers(event))

    fcd['requestor'] = request_info['user_arn']
    fcd['requestid'] = request_info['request_id']
    business_unit = account_info['data']['accounts'][0]['businessUnit']

    try:
        # TODO: Short circuit to framework state machine. Only allow BT accounts for now.
        # Also only allow it in dev
        # Remove this after framework cutover
        if "framework" in fcd and business_unit == "Braintree" and fcd['environment'] == "DEV":
            logging.info(f"Short circuiting to framework state machine for Braintree DEV account {fcd['account']}.")
            business_unit = "Framework"

        state_machine_arn = STATE_MACHINE_ARNS[business_unit]
    except KeyError as e:
        return send_response(400, f"Account {fcd['account']} has an unrecognized BU {business_unit}", get_headers(event))

    logging.info(
        f"Attempting to start state machine %s for account %s with FCD %s",
        state_machine_arn,
        fcd['account'],
        fcd,
    )
    
    try:
        is_execution_in_progress, execution_arn = check_execution_status(fcd['account'], fcd['region']) 
        if is_execution_in_progress is True:
            logging.warning('Another execution is in progress (ARN: %s). Try again later.', execution_arn)
            return send_response(400, f"Another execution is in progress (ARN: {execution_arn}). Please try again later.", get_headers(event))
    except Exception as exception: 
        return send_response(400, f"Encountered error when looking up active executions: {str(exception)}", get_headers(event))

    state_file_bucket(ORCHESTRATION_REGION, state_machine_arn)
    state_machine_data = start_state_machine(state_machine_arn, json.dumps(fcd), ORCHESTRATION_REGION)

    # Generate BUs deployer list to hydrate in SOR
    deployers = []

    # If we can't find the BU in our mapping we default to Braintree BU state machine
    for deployer in DEPLOYERS_PER_BU.get(business_unit, DEPLOYERS_PER_BU["Braintree"]):
        deployers.append(
            {
                "name": deployer,
                "status": "Not_Started",
                "version": "Unknown",
                "outputs": {},
            }
        )

    query_variables = {
        "accountId": fcd['account'],
        "executionArn": state_machine_data['execution_arn'],
        "startTime": str(state_machine_data['start_date']).replace(' ', 'T'),
        "type": "BASELINE",
        "status": "IN_PROGRESS",
        "configurationDocument": fcd,
        "deployers": deployers,
        "region": fcd['region']
    }

    try:
        execution_create_response = execute_sor_query(CREATE_EXECUTION_MUTATION, query_variables)
    except Exception as e:
        return send_response(400, f"Encountered error when attempting to hydrate SOR with account execution. {str(e)}", get_headers(event))

    logging.info('Successfully hydrated data to SOR: %s.', execution_create_response)
    success_message = "Request successfully submitted. Please use the /status API to check the status of the execution. Execution ARN: " + state_machine_data['execution_arn']
    response = send_response(200, success_message, get_headers(event), resource_id=state_machine_data['execution_arn'])
    return response
