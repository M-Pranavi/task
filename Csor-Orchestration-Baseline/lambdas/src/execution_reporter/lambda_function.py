"""Lambda function to write report execution status of orchestration"""

import json
import os
import sys
import logging
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session

LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
STACKTRACE_LIMIT: int = int(os.getenv('STACKTRACE_LIMIT', '10'))
REGION: str = str(os.getenv('REGION', 'us-east-2')).lower()
SOR_ENDPOINT = os.getenv("SOR_ENDPOINT")
if not SOR_ENDPOINT:
    raise KeyError("Failed to get the SOR_ENDPOINT")


def configure_logging(log_level: str = 'info', traceback_limit: int = 10):
    """Configure the root logger and stacktrace setting for the lambda."""
    logging.getLogger().setLevel(str(log_level).upper())
    logging.info('Log level is set to %s.', log_level)
    if log_level.upper() == "DEBUG":
        sys.tracebacklimit = traceback_limit
        logging.debug('Stack traceback limit is %s.', traceback_limit)
    else:
        sys.tracebacklimit = 0
        logging.info('Stack traceback is disabled.')
        
        
def __get_env_variable(var_name, default=None):
    """Retrieve an environment variable with an optional default."""
    return os.getenv(var_name, default)


def sign_request(url, method, headers, body):
    """Sign the request using SigV4"""
    session = get_session()
    credentials = session.get_credentials().get_frozen_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, 'execute-api', os.getenv('REGION')).add_auth(request)
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


def update_execution_status_sor(execution_arn: str, execution_status: str):
    """Update state machine execution status in SOR."""
    mutation_query = """
    mutation UpdateExecutionStatus($executionArn: String!, $executionStatus: OrchestrationStatus!) {
        updateStateMachineExecution(executionArn: $executionArn, status: $executionStatus) {
            arn
            status
        }
    }
    """
    variables = {"executionArn": execution_arn, "executionStatus": execution_status}
    try:
        response = execute_sor_query(mutation_query, variables)
        logging.info('Execution status updated: %s', response)
        return response
    except Exception as exception:
        error_msg = "Failed to update execution status due to: %s", exception
        logging.error(error_msg)
        return {'error': error_msg}


def lambda_handler(event, context):
    """Entry point for the Lambda function."""
    configure_logging(LOG_LEVEL, STACKTRACE_LIMIT)
    logging.info('Lambda event: %s', event)
    logging.debug('Lambda context: %s', context)
    execution_arn = event['detail']['executionArn']
    execution_status = event['detail']['status']
    
    if not __get_env_variable("SOR_ENDPOINT"):
        raise KeyError("No SoR endpoint set") 

    response = update_execution_status_sor(execution_arn, execution_status)
    logging.info("SOR status: %s", response)
