"""Lambda to write to DynamoDB."""

import json
import logging
import os
import re
import sys
from typing import Dict, Tuple, Optional
import botocore
import botocore.exceptions
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session

STATE_FILE_PREFIX: str = 'csor-orchestration-provision-statefiles-'

STATE_MACHINE_ARNS: dict = json.loads(os.getenv('STATE_MACHINE_ARNS', "{}"))
ORCHESTRATION_REGION: str = str(os.getenv('ORCHESTRATION_REGION', 'us-east-2')).lower()
TENANT_REGION: str = str(os.getenv('TENANT_REGION', 'us-east-2')).lower()
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

PROVISION_ROLE: str = os.getenv('PROVISION_ROLE', 'arn:aws:sts::1234567890:assumed-role/csor-nonprod-env-jenkins-service-account-role/e2e_provision')

DEPLOYERS_PER_BU: dict = {
    "Braintree": [
        "base_deployer",
        "stackset_deployer",
        "eks_deployer",
        "kap_deployer",
    ],
    # TODO: Remove after framework cutover. Used for routing in testing
    "Framework": [
        "base_deployer",
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

CREATE_ACCOUNT_EXECUTION_MUTATION = """
    mutation ($executionArn: String!, $accountId: String!, $type: StateMachine!, $status: OrchestrationStatus!, $startTime: ISO8601DateTime!,
        $deployers: [DeployerInput!]!, $configurationDocument: JSON!, $region: Region!){
      createStateMachineExecution(accountId: $accountId, executionArn: $executionArn, type: $type, startTime: $startTime, status: $status,
        deployers: $deployers, configurationDocument: $configurationDocument, region:$region) {
        arn
        status
        startTime
        region
        deployers {
          name
          status
        }
        configurationDocument
      }
    }
"""

VALIDATE_ACCOUNT_INFO = """
    query ($accountId: String!, $region: Region!) {
        accounts(id: $accountId, region: $region) {
            id
            name
            accountType
            regions
            businessUnit
            baseline {
                lastSuccess {
                    status
                }
            }
        }
    }
"""

ACCOUNT_EXECUTIONS = """
    query ($id: String!, $region: Region!) {
        accounts(id: $id, region: $region) {
            id
            appInfra {
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


class Error:
    def __init__(self,
                 status_code,
                 status_description,
                 failure_message):
        self.status_code = status_code
        self.status_description = status_description
        self.failure_message = failure_message

    def exception(self):
        return {
            'statusCode': self.status_code,
            'body': json.dumps(
                {
                    "status_code": str(self.status_code) + "-" + self.status_description,
                    "reason": self.failure_message
                }
            ),
            'isBase64Encoded': False,
            'headers': {
                'Content-Type': 'application/json'
            },
        }


def send_response(http_code, body, event_headers=None, resource_id=None):
    """Send response back to the client."""
    content_type = "application/json"
    body = {"message": body}
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


def sign_request(url, method, headers, body):
    """Sign using SigV4"""
    session = get_session()
    credentials = session.get_credentials().get_frozen_credentials()
    #Making sure that headers do not contain None
    headers = {k: v for k, v in headers.items() if v is not None}
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
        msg = f"Failed to communicate with API: {api_url}. Code: {response.status_code}, Reason: {response.reason}, Text: {response.text}"
        raise requests.exceptions.RequestException(msg)

    return response.json()


def execute_sor_query(query: str, variables: dict = None) -> dict:
    """Invoke the GraphQL query via API Gateway"""

    sor_endpoint = os.getenv('SOR_ENDPOINT')
    raw_query = {
        "query": query,
        "variables": variables or {}
    }
    response = invoke_api_gateway(
        api_url=sor_endpoint,
        raw_query=raw_query
    )

    if 'errors' in response:
        raise RuntimeError(f"GraphQL returned errors: {response}")

    return response


def start_state_machine(state_machine_arn: str, bom: str, region: str):
    """Execute the target statemachine with the supplied bill of materials."""
    result: Dict[str, str] = {
        'execution_arn': 'undefined',
        'start_date': 'undefined'
    }
    try:
        client = boto3.client(
            service_name='stepfunctions',
            region_name=region)
        response = client.start_execution(input=bom,
                                          stateMachineArn=state_machine_arn)
        result = {'execution_arn': response['executionArn'],
                  'start_date': response['startDate']}
    except botocore.exceptions.ClientError as err:
        raise err
    logging.debug('State machine response:\n%s', response)
    return result


def configure_logging(log_level: str = 'INFO'):
    """Configure the root logger for the lambda."""
    logging.getLogger().setLevel(log_level.upper())


def verify_account_id(bom: dict, caller_account_id, user_arn) -> bool:
    """
    Checks the account ID, except for provision_role.
    """
    bom_id = bom['account']

    try:
        caller_role = user_arn.split('/')[-2] if user_arn else None
        logging.info('IAM Role that called this function: %s', user_arn)
    except KeyError:
        logging.warning('userArn not found; caller_role cannot be extracted')
        caller_role = None

    expected_role_name = PROVISION_ROLE.split('/')[-1] if PROVISION_ROLE else None
    logging.info('Jenkins Role Name: %s', PROVISION_ROLE)

    if PROVISION_ROLE and caller_role == expected_role_name:
        return True

    return bom_id == caller_account_id


def validate_provision_request(bom, validation_response) -> (bool, str):
    # Cases: 1. No data 2. Not onboarded yet
    if not (validation_response['data']) or not (validation_response['data']['accounts']):
        return False, "The Account ID in the provision BOM does not exist in SOR"
    elif bom['region'] not in validation_response['data']['accounts'][0]['regions']:
        return False, f"The Account ID {bom['account']} cannot be provisioned in this region {bom['region']}"
    # Cases: 1. Not Baselined 2. No latest successful baseline runs
    elif not validation_response['data']['accounts'][0]['baseline']:
        return False, "The Account ID in the provision BOM has not been baselined yet"
    # Cases: 1. Last Successful baseline execution is null 2. Last Successful baseline status: ABORTED/FAILED/IN_PROGRESS/TIMED_OUT
    elif validation_response['data']['accounts'][0]['baseline'][0]['lastSuccess'] is None or validation_response['data']['accounts'][0]['baseline'][0]['lastSuccess'] == "null" or \
            validation_response['data']['accounts'][0]['baseline'][0]['lastSuccess']['status'] != "SUCCEEDED":
        return False, "The Account ID in the provision BOM has not been successfully baselined yet"
    else:
        return True, ""


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


def create_buckets(bucket_region: str, bucket_name: str) -> bool:
    s3_client = boto3.client('s3', region_name=bucket_region)
    bucket_name_replication = bucket_name + "-replica"
    try:
        s3_client.create_bucket(Bucket=bucket_name,
                                CreateBucketConfiguration={'LocationConstraint': bucket_region})
        logging.info("Created state file bucket: %s", bucket_name)
        s3_client.create_bucket(Bucket=bucket_name_replication,
                                CreateBucketConfiguration={'LocationConstraint': bucket_region})
        logging.info("Created state file bucket: %s", bucket_name_replication)
        # activating the versioning
        try:
            s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={
                    'Status': 'Enabled'
                }
            )
            logging.info(f"Bucket versioning enabled for {bucket_name}")
            s3_client.put_bucket_versioning(
                Bucket=bucket_name_replication,
                VersioningConfiguration={
                    'Status': 'Enabled'
                }
            )
            logging.info(f"Bucket versioning enabled for {bucket_name_replication}")
            configure_replication(bucket_name, bucket_name_replication)
        except s3_client.exceptions.ClientError as e:
            logging.error(f"Failed to enable versioning on the bucket: {e}")
            raise e
    except s3_client.exceptions.ClientError as e:
        logging.error("Failed to create bucket: %s", e)
        raise e
    return


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

        REPLICATION_POLICY: dict = {
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
        policy_response = iam_client.put_role_policy(
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


def get_headers(event):
    return event['headers'] if 'headers' in event else None


def check_execution_status(account_id: str, tenant_region: str) -> Tuple[bool, Optional[str]]:
    variables = {"id": account_id, "region": tenant_region}
    response = execute_sor_query(ACCOUNT_EXECUTIONS, variables)
    logging.info('SOR Response: %s', response)

    region_summaries = response['data']['accounts'][0]['appInfra']
    for region_summary in region_summaries:
        latest_execution = region_summary.get('latest')
        if latest_execution:
            last_execution_status = latest_execution['status']
            execution_arn = latest_execution['arn']
            if last_execution_status == "IN_PROGRESS":
                logging.info('Account ID %s: Execution in progress with ARN %s.', account_id, execution_arn)
                return True, execution_arn
    return False, None


def parse_request_info(request_context):
    """Retrieve request information from the event request context."""
    request_id = request_context['requestId']

    # Fetch user information
    user_arn = request_context['identity']['userArn']
    caller = re.findall('arn:aws:sts::[0-9]+:assumed-role/.*/(.*)', user_arn)[0]
    caller_account_id = request_context['identity']['accountId']

    return {
        "user_arn": user_arn,
        "caller": caller,
        "request_id": request_id,
        "caller_account_id": caller_account_id,
    }


def lambda_handler(event: dict, context: dict) -> dict:
    """Execute lambda process."""
    configure_logging(LOG_LEVEL)

    request_info = parse_request_info(event['requestContext'])

    logging.info(
        "Received new request: ID: %s, Caller: %s",
        request_info['request_id'],
        request_info['caller'],
    )

    logging.debug(
        "Lambda received event: %s\n with context: %s\n",
        event,
        context,
    )

    try:
        bom = json.loads(event['body'])
    except json.JSONDecodeError:
        return send_response(400, str(ValueError('Invalid bill of materials: Invalid JSON')), get_headers(event))

    if not verify_account_id(bom, request_info['caller_account_id'], request_info['user_arn']):
        failure_message = f"The caller AWS Account ID {request_info['caller_account_id']} does not match the BOM account ID {bom['account']}"
        return Error(status_code=400, status_description="Invalid Request", failure_message=failure_message).exception()

    try:
        query_variables = {
            "accountId": bom['account'],
            "region": bom['region']
        }
        account_info = execute_sor_query(VALIDATE_ACCOUNT_INFO, query_variables)
        is_validated, failure_message = validate_provision_request(bom, account_info)
    except Exception as e:
        return send_response(400, f"Encountered error when trying to validate provision request: {str(e)}")

    if not is_validated:
        logging.error("%s", failure_message)
        return Error(status_code=400, status_description="Invalid Request", failure_message=failure_message).exception()

    try:
        is_execution_in_progress, execution_arn = check_execution_status(bom['account'], bom['region'])
        if is_execution_in_progress is True:
            logging.warning('Another execution is in progress (ARN: %s). Try again later.', execution_arn)
            return send_response(400, f"Another execution is in progress (ARN: {execution_arn}). Please try again later.")
    except Exception as exception:
        return send_response(400, f"Encountered error when looking up active executions: {str(exception)}")

    bom['requestor'] = request_info['caller']
    bom['requestid'] = request_info['request_id']
    business_unit = account_info['data']['accounts'][0]['businessUnit']

    try:
        # TODO: Short circuit to framework state machine. Only allow BT accounts for now.
        # Also only allow it in dev
        # Remove this after framework cutover
        if "framework" in bom and business_unit == "Braintree" and bom['environment'] == "DEV":
            logging.info(f"Short circuiting to framework state machine for Braintree DEV account {bom['account']}.")
            business_unit = "Framework"

        state_machine_arn = STATE_MACHINE_ARNS[business_unit]
    except KeyError as e:
        return send_response(400, f"BU {business_unit} for account {bom['account']} is unsupported in CSoR provision", get_headers(event))

    logging.info(
        f"Attempting to start state machine %s for account %s with BOM %s",
        state_machine_arn,
        bom['account'],
        bom,
    )

    state_file_bucket(ORCHESTRATION_REGION, state_machine_arn)
    state_machine_data = start_state_machine(state_machine_arn, json.dumps(bom), ORCHESTRATION_REGION)

    # Generate BU specific deployers list. If we can't find the BU we default to Braintree BU state machine deployers
    # This is safe as invalid BUs will have already been given an error
    deployers = []

    for deployer in DEPLOYERS_PER_BU.get(business_unit, DEPLOYERS_PER_BU['Braintree']):
        deployers.append(
            {
                "name": deployer,
                "status": "Not_Started",
                "version": "Unknown",
                "outputs": {},
            }
        )

    query_variables = {
        "accountId": bom['account'],
        "executionArn": state_machine_data['execution_arn'],
        "startTime": str(state_machine_data['start_date']).replace(' ', 'T'),
        "type": "PROVISION",
        "status": "IN_PROGRESS",
        "configurationDocument": bom,
        "deployers": deployers,
        "region": bom['region']
    }

    try:
        execution_create_response = execute_sor_query(CREATE_ACCOUNT_EXECUTION_MUTATION, query_variables)
    except Exception as e:
        return send_response(500, f'Encountered error when attempting to hydrate SOR with account execution. {str(e)}', get_headers(event))

    logging.info('Successfully hydrated data to SOR: %s', execution_create_response)
    success_message = "Request successfully submitted. Please use the /status API to check the status of the execution."
    response = send_response(200, success_message, get_headers(event), resource_id=state_machine_data['execution_arn'])
    return response
