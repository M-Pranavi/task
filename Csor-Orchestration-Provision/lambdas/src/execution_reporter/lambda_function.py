"""Lambda function to write report execution status of orchestration"""

import json
import logging
import os
import sys

import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session
from gql import gql

LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
STACKTRACE_LIMIT: int = int(os.getenv('STACKTRACE_LIMIT', '10'))
ORCHESTRATION_REGION: str = str(os.getenv('ORCHESTRATION_REGION', 'us-east-2')).lower()
MUTATION_QUERY = """
    mutation UpdateExecutionStatus($executionArn: String!, $executionStatus: OrchestrationStatus!) {
        updateStateMachineExecution(executionArn: $executionArn, status: $executionStatus) {
            arn
            status
        }
    }
"""

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

def sign_request(url, method, headers, body):
    """Sign using SigV4"""
    session = get_session()
    credentials = session.get_credentials().get_frozen_credentials()

    #Making sure that headers do not contain None
    headers = {k:v for k,v in headers.items() if v is not None}
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, 'execute-api', os.getenv('ORCHESTRATION_REGION')).add_auth(request)
    return request

def invoke_api_gateway(api_url, raw_query=None):
    """Invoke API Gateway"""
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

def execute_sor_query(query: str, variable_values: dict = None) -> dict:
    
    sor_endpoint = os.getenv('SOR_ENDPOINT')
    if not sor_endpoint:
        raise KeyError("Failed to get the SOR_ENDPOINT")
    raw_query = {
        "query": query,
        "variables": variable_values or {}
    }

    response = invoke_api_gateway(
        api_url=sor_endpoint,
        raw_query=raw_query
    )

    if 'errors' in response:
        raise RuntimeError(f"GraphQL returned errors: {response}")
    return response

def update_execution_status_sor(execution_arn: str, execution_status: str):
    """Update state machine execution status in SOR."""
    params= {"executionArn": execution_arn, "executionStatus": execution_status}
    try:
        response = execute_sor_query(MUTATION_QUERY, variable_values=params)
        logging.info('Execution status updated: %s', response)
        return response
    except Exception as e:
        error_msg = f'Failed to update execution status due to: {e}'
        logging.error(error_msg)
        return {'error': error_msg}

def lambda_handler(event, context):
    """Entry point for the Lambda function."""
    configure_logging(LOG_LEVEL, STACKTRACE_LIMIT)
    logging.info('Lambda event: %s', event)
    logging.debug('Lambda context: %s', context)
    execution_arn = event['detail']['executionArn']
    execution_status = event['detail']['status']
    response = update_execution_status_sor(execution_arn, execution_status)
    logging.info("SOR status: %s", response)
