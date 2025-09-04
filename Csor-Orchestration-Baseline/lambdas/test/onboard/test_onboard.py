from unittest.mock import patch
import json
from pytest import fixture
from lambdas.src.onboard.lambda_function import lambda_handler, client_response, send_request_to_graphql, get_requestor, get_request_id, CREATE_ACCOUNT_QUERY


VARIABLES = '''
    {
        "accountId": "616954419039",
        "name": "dev-bt-logging",
        "type": "FOUNDATION",
        "environment": "DEV",
        "owner": "ianisimau",
        "applicationName": "csor-logging-foundation",
        "distributionList": "cloudnx@paypal.com",
        "slackServiceChannel": "bt-csor-collab",
        "businessUnit": "Braintree",
        "dataClassification": "CLASS_4",
        "businessCriticality": "CRITICAL",
        "connectivity": "INTERNAL",
        "baselineChangeApprovalRequired": false,
        "provisionChangeApprovalRequired": false
    }
'''

RETURN_BODY = {"data":{"createAccount":{"id":"616954419039","name":"dev-bt-logging","environment":"DEV"}}}

SAMPLE_EVENT: dict = {
    "requestContext": {
        "elb": {
            "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-2:614751254790:targetgroup/tf-2023090118450943010000000a/86bcbf421ea1f4ab"
        },
        "identity": {
            "userArn": "arn:aws:sts::123456789123:assumed-role/assumed_scope_role_root/davcarroll"
        },
        "requestId": "f8a8b82c-dd1e-420a-a535-3bd102f22c01"
    },
    "httpMethod": "POST",
    "path": "/",
    "queryStringParameters": {},
    "headers": {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "connection": "keep-alive",
        "content-length": "468",
        "content-type": "application/json",
        "host": "orchestration-alb-888937532.us-east-2.elb.amazonaws.com",
        "postman-token": "4ac627e2-9b04-426f-85ae-79560e307b35",
        "user-agent": "PostmanRuntime/7.29.2",
        "x-amzn-trace-id": "Root=1-656a06c9-3de2ee42081172641a1fa1f7",
        "x-forwarded-for": "189.113.229.236, 147.161.129.8:43709",
        "x-forwarded-port": "443",
        "x-forwarded-proto": "https"
    },
    "body": json.dumps(VARIABLES),
    "isBase64Encoded": False
}

@fixture(autouse=True)
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("SOR_ENDPOINT", "https://sor.endpoint")

@patch('lambdas.src.onboard.lambda_function.invoke_api_gateway')
def test_send_request_to_graphql(mock_invoke_api_gateway):
    mock_response = RETURN_BODY
    mock_invoke_api_gateway.return_value = mock_response

    endpoint = "https://example.com"
    variables = VARIABLES
    query = CREATE_ACCOUNT_QUERY
    region = "us-east-2"

    response = send_request_to_graphql(endpoint, variables, query, region)
    assert response == mock_response

def test_client_response():
    response = client_response(200, RETURN_BODY)
    expected_response = {
        'statusCode': 200,
        'isBase64Encoded': False,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': {"data":{"createAccount":{"id":"616954419039","name":"dev-bt-logging","environment":"DEV"}}}
    }
    assert response == expected_response

@patch('lambdas.src.onboard.lambda_function.send_request_to_graphql')
def test_lambda_handler_success(mock_send_request_to_graphql):
    mock_send_request_to_graphql.return_value = {
        'statusCode': 200,
        'isBase64Encoded': False,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': RETURN_BODY
    }
    response = lambda_handler(SAMPLE_EVENT, {})
    assert response['statusCode'] == 200
    assert response['body'] == "{'statusCode': 200, 'isBase64Encoded': False, 'headers': {'Content-Type': 'application/json'}, 'body': {'data': {'createAccount': {'id': '616954419039', 'name': 'dev-bt-logging', 'environment': 'DEV'}}}}"

def test_lambda_handler_invalid_json():
    SAMPLE_EVENT['body'] = 'invalid'

    response = lambda_handler(SAMPLE_EVENT, {})
    assert response['statusCode'] == 400
    assert 'Invalid account info: Invalid JSON' in response['body']

def test_parse_caller_id():
    """Test that we can correctly parse the caller from the request context."""
    caller = get_requestor(SAMPLE_EVENT)
    assert caller == "davcarroll"

def test_request_id():
    """Test to retreieve the request_id from the events."""
    request_id = get_request_id(SAMPLE_EVENT)
    assert request_id == "f8a8b82c-dd1e-420a-a535-3bd102f22c01"
