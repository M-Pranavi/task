"""Lambda function to onboard a new account to SOR"""

import json
import os
import logging
import requests
import sys
import re
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session

LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
REGION: str = str(os.getenv('REGION', 'us-east-2')).lower()

STATUS_OK = 200
JSON_DECODE_ERROR = 400
INTERNAL_SERVER_ERROR = 500
STACKTRACE_LIMIT: int = int(os.getenv('STACKTRACE_LIMIT', '10'))

CREATE_ACCOUNT_QUERY = '''
                      mutation ($accountId:String!, 
                      $name:String!,
                      $type:AccountType!,
                      $environment:Environment!,
                      $owner:String!,
                      $applicationName:String!,
                      $distributionList:String!,
                      $slackServiceChannel:String!,
                      $businessUnit:String!,
                      $dataClassification:DataClassification!,
                      $businessCriticality:BusinessCriticality!,
                      $connectivity:AccountConnectivity!,
                      $baselineChangeApprovalRequired: Boolean!,
                      $provisionChangeApprovalRequired: Boolean!,
                      $regions: [Region!]!) {
              createAccount(accountId:$accountId,
                            name:$name,
                            type:$type,
                            environment:$environment,
                            owner:$owner,
                            applicationName:$applicationName,
                            distributionList:$distributionList,
                            slackServiceChannel:$slackServiceChannel,
                            businessUnit:$businessUnit,
                            dataClassification:$dataClassification,
                            businessCriticality:$businessCriticality,
                            connectivity:$connectivity,
                            baselineChangeApprovalRequired: $baselineChangeApprovalRequired,
                            provisionChangeApprovalRequired: $provisionChangeApprovalRequired,
                            regions: $regions)
              {
                id
                name
                environment
              }
            }
  '''

def configure_logging(log_level: str = 'debug', traceback_limit: int = 10):
    """Configure the root logger and stacktrace setting for the lambda."""
    logging.getLogger().setLevel(str(log_level).upper())
    logging.info('Log level is set to %s.', log_level)
    if log_level.upper() == "DEBUG":
        sys.tracebacklimit = traceback_limit
        logging.debug('Stack traceback limit is %s.', traceback_limit)
    else:
        sys.tracebacklimit = 0
        logging.info('Stack traceback is disabled.')

def sign_request(url, method, headers, body, region):
    """Sign the request using SigV4"""
    session = get_session()
    credentials = session.get_credentials().get_frozen_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, 'execute-api', region).add_auth(request)
    return request

def invoke_api_gateway(api_url, raw_query, region):
    """Invoke API Gateway with SigV4 signing"""
    headers = {
        'Content-Type': 'application/json'
    }
    body = json.dumps(raw_query)
    signed_request = sign_request(api_url, 'POST', headers, body, region)
    response = requests.post(api_url, data=signed_request.body, headers=dict(signed_request.headers.items()), timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"SOR request failed with status code {response.status_code}. Response {response.text}")
    return response.json()

def send_request_to_graphql(endpoint: str, variables: dict, query: str, region: str):
    """Send mutation to GraphQL endpoint."""
    try:
        response = invoke_api_gateway(endpoint, {"query": query, "variables": variables}, region)
        logging.info("GraphQL response: %s", response)
        if "errors" in response:
            raise RuntimeError(f"SOR returned error: {response}")

        return response
    except Exception as err:
        logging.error("Error querying GraphQL: %s", err)
        raise

def client_response(http_code, body):
    """Send response back to the client."""
    response = {
        'statusCode': http_code,
        'isBase64Encoded': False,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': body
    }
    logging.info("Client response: %s", response)
    return response

def get_requestor(event):
    """Retrieve the requestor from the event"""
    user_arn = event['requestContext']['identity']['userArn']
    caller = re.findall('arn:aws:sts::[0-9]+:assumed-role/.*/(.*)', user_arn)[0]
    return caller

def get_request_id(event):
    """Retrieve requestID from the event"""
    return  event['requestContext']['requestId']

def lambda_handler(event, context):
    """Entry point for the Lambda function."""
    configure_logging(LOG_LEVEL, STACKTRACE_LIMIT)
    logging.info("Processing onboard request: %s", event)
    logging.info('Requestor: %s', get_requestor(event))
    logging.info("RequestId: %s", get_request_id(event))

    SOR_ENDPOINT = os.getenv("SOR_ENDPOINT")
    if not SOR_ENDPOINT:
        return client_response(INTERNAL_SERVER_ERROR, "Internal Error: Failed to retrieve SOR_ENDPOINT from environment variables.")

    try:
        account_info = json.loads(event['body'])
        logging.info("Parsed the following account onboard info: %s", account_info)
        gql_response = send_request_to_graphql(SOR_ENDPOINT, account_info, CREATE_ACCOUNT_QUERY, REGION)
        response = client_response(STATUS_OK, str(gql_response))
    except json.JSONDecodeError:
        response = client_response(JSON_DECODE_ERROR, str(ValueError("Invalid account info: Invalid JSON")))
    except Exception as e:
        response = client_response(INTERNAL_SERVER_ERROR, str(e))

    return response
