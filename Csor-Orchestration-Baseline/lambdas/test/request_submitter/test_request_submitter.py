import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from lambdas.src.request_submitter import lambda_function

os.environ['DOCKER_REGISTRY'] = '123456789111.dkr.ecr.us-east-2.amazonaws.com'

SAMPLE_BOM: dict = {
    "account": "081297776604",
    "name": "dev-bt-app1",
    "environment": "DEV",
    "region": "us-east-2",
    "base_deployer": "1.0.0",
    "stackset_deployer": "1.0.0"
}

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
    "body": json.dumps(SAMPLE_BOM),
    "isBase64Encoded": False
}


@pytest.fixture(autouse=True)
def ecr():
    sample_digest = {"mediaType": ""}
    with mock_aws():
        client = boto3.client('ecr', region_name='us-east-2')
        client.create_repository(registryId='123456789111', repositoryName='baseline_base_deployer')
        client.create_repository(registryId='123456789111', repositoryName='stackset_deployer')
        client.create_repository(registryId='123456789111', repositoryName='security_shield_deployer')
        client.create_repository(registryId='123456789111', repositoryName='cicd_deployer')
        client.create_repository(registryId='123456789111', repositoryName='network_deployer')
        client.create_repository(registryId='123456789111', repositoryName='logging_deployer')

        client.put_image(repositoryName='baseline_base_deployer', imageManifest=json.dumps(sample_digest), imageTag='1.0.0')
        client.put_image(repositoryName='stackset_deployer', imageManifest=json.dumps(sample_digest), imageTag='1.0.0')
        client.put_image(repositoryName='security_shield_deployer', imageManifest=json.dumps(sample_digest), imageTag='1.0.0')
        client.put_image(repositoryName='cicd_deployer', imageManifest=json.dumps(sample_digest), imageTag='1.0.0')
        client.put_image(repositoryName='network_deployer', imageManifest=json.dumps(sample_digest), imageTag='1.0.0')
        client.put_image(repositoryName='logging_deployer', imageManifest=json.dumps(sample_digest), imageTag='1.0.0')
        yield


@pytest.fixture(autouse=True)
def state_machines():
    with mock_aws():
        client = boto3.client(service_name='stepfunctions', region_name='us-east-2')
        business_units = ["Apollo", "Braintree", "Chargehound"]
        step_functions = {}
        for bu in business_units:
            state_machine = client.create_state_machine(
                name=bu,
                definition='{"StartAt": "HelloWorld", "States": {"HelloWorld": {"Type": "Pass", "Result": "Hello, World!", "End": True}}}',
                roleArn='arn:aws:iam::123456789012:role/service-role/StepFunctions-HelloWorld'
            )
            step_functions[bu] = state_machine['stateMachineArn']

        step_functions["PCIS"] = step_functions["Braintree"]
        lambda_function.STATE_MACHINE_ARNS = step_functions
        yield


@pytest.fixture(autouse=True)
def patch_state_file_bucket():
    with patch('lambdas.src.request_submitter.lambda_function.state_file_bucket') as mock_bucket:
        mock_bucket.return_value = {}
        yield


@pytest.fixture(autouse=True)
def patch_sor_signing():
    with patch('lambdas.src.request_submitter.lambda_function.sign_request') as mock_sign:
        mock_sign.return_value = SimpleNamespace(**{"body": "hello", "headers": {"1": "2"}})
        yield


def test_parse_request_info():
    """Test we can properly parse request info"""
    request_context = {"identity": {"userArn": "arn:aws:sts::12345:assumed-role/my-role/davcarroll"}, "requestId": "1234"}
    request_info = lambda_function.parse_request_info(request_context)

    assert request_info['user_arn'] == "davcarroll"
    assert request_info['request_id'] == "1234"


def test_invalid_bom_format():
    """Test failure with invalid bom format"""
    invalid_bom_event = {
        "body": "{",
        "requestContext": {"identity": {"userArn": "arn:aws:sts::12345:assumed-role/my-role/davcarroll"}, "requestId": "1234"}
    }

    response = lambda_function.lambda_handler(invalid_bom_event, {})
    assert response
    assert response['statusCode'] == 400
    assert "invalid JSON" in response['body']


def test_invalid_bom_versions():
    """Test invalid bom versions"""
    invalid_bom = {"base_deployer": "1.5.0"}
    invalid_bom_event = {
        "body": json.dumps(invalid_bom),
        "requestContext": {"identity": {"userArn": "arn:aws:sts::12345:assumed-role/my-role/davcarroll"}, "requestId": "1234"}
    }

    response = lambda_function.lambda_handler(invalid_bom_event, {})
    assert response
    assert response['statusCode'] == 400
    assert "Image 1.5.0 not found for baseline_base_deployer" in response['body']


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_broken_sor_communication(mock_post):
    """Test unable to communicate with sor"""
    mock_post.return_value.status_code = 500
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Encountered error when looking up account" in response["body"]
    assert "Code: 500" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_invalid_sor_communication(mock_post):
    """Test errors when communicating with SOR"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"errors": "My error"}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Encountered error when looking up account" in response["body"]
    assert "My error" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_account_not_onboarded(mock_post):
    """Test attempt to baseline an account that is not onboarded"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {"accounts": []}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Account has not been onboarded" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_account_invalid_region(mock_post):
    """Test attempt to baseline a region not supported by account"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-1"]}]}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Requested region 'us-east-2' is not in list" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_request_submitter(mock_post):
    """Test full request submitter flow"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [
        {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-2"], "businessUnit": "Braintree"}]}},
        {"data": {"accounts": [{"baseline": [{"latest": {"startTime": "2023-10-01T00:00:00Z", "status": "SUCCESS", "arn": "mock-execution-arn"}}]}]}},
        {"data": ""},
    ]
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 200
    assert 'execution:Braintree' in response['body']
    assert 'Request successfully submitted' in response['body']


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_request_submitter_multi_bu(mock_post):
    """Test that we can handle multiple business units"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [
        {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-2"], "businessUnit": "Apollo"}]}},
        {"data": {"accounts": [{"baseline": [{"latest": {"startTime": "2023-10-01T00:00:00Z", "status": "SUCCESS", "arn": "mock-execution-arn"}}]}]}},
        {"data": ""},
    ]
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 200
    assert 'execution:Apollo' in response['body']
    assert 'Request successfully submitted' in response['body']


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_request_submitter_multi_bu_with_default(mock_post):
    """Test that we can handle multiple business units and default to Braintree if we can't find the BU"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [
        {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-2"], "businessUnit": "PCIS"}]}},
        {"data": {"accounts": [{"baseline": [{"latest": {"startTime": "2023-10-01T00:00:00Z", "status": "SUCCESS", "arn": "mock-execution-arn"}}]}]}},
        {"data": ""},
    ]
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 200
    assert 'execution:Braintree' in response['body']
    assert 'Request successfully submitted' in response['body']


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_unsupported_bu(mock_post):
    """Test that we return an error on unsupported BUs"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [
        {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-2"], "businessUnit": "MY_BU"}]}},
        {"data": {"accounts": [{"baseline": [{"latest": {"startTime": "2023-10-01T00:00:00Z", "status": "SUCCESS", "arn": "mock-execution-arn"}}]}]}},
        {"data": ""},
    ]
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert 'Account 081297776604 has an unrecognized BU MY_BU' in response['body']


def build_request_context(request_id, account_id, user_id):
    return {'requestId': request_id, 'identity': {'userArn': 'arn:aws:sts::{}:assumed-role/{}'.format(account_id, user_id)}}


@patch('lambdas.src.request_submitter.lambda_function.invoke_api_gateway')
@mock_aws
def test_returns_400_with_message_when_account_has_not_been_onboarded(mock_invoke_api_gateway):
    sample_bom = {
        "account": "12131124232323242314",
        "name": "not-a-real-account",
        "environment": "DEV",
        "region": "not-a-real-region",
        "base_deployer": "1.0.0",
        "cicd_deployer": "1.0.0",
        "network_deployer": "1.0.0",
        "logging_deployer": "1.0.0",
        "security_shield_deployer": "1.0.0",
        "stackset_deployer": "1.0.0"
    }

    mock_invoke_api_gateway.return_value = {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-1"], "businessUnit": "Braintree"}]}}

    request_context = build_request_context("someRequestID", "123456789", "some/userARN")
    response = lambda_function.lambda_handler({'body': json.dumps(sample_bom), 'requestContext': request_context}, {})

    assert response == {
        'headers': {'Content-Type': 'application/json'},
        'isBase64Encoded': False,
        'statusCode': 400,
        'body': json.dumps(
            {
            'message':'Account has not been onboarded. Please onboard it using runbook: https://paypal.atlassian.net/wiki/spaces/BTSRE/pages/939401510/Onboard+AWS+Account+to+CSoR'
            }
            )
    }

@patch('lambdas.src.request_submitter.lambda_function.invoke_api_gateway')
@mock_aws
def test_returns_400_with_message_when_account_has_not_been_onboarded_in_json_format_when_accept_header_contains_application_json(mock_invoke_api_gateway):
    request_context = build_request_context("someRequestID", "123456789", "some/userARN")
    mock_invoke_api_gateway.return_value
    response = lambda_function.lambda_handler({'body': json.dumps(SAMPLE_BOM), 'requestContext': request_context, 'headers': {'accept': 'application/json'}}, {})

    assert response['statusCode'] == 400
    assert response['headers']['Content-Type'] == 'application/json'
    response_body = json.loads(response['body'])
    assert response_body['message'] == "Account has not been onboarded. Please onboard it using runbook: https://paypal.atlassian.net/wiki/spaces/BTSRE/pages/939401510/Onboard+AWS+Account+to+CSoR"

    response = lambda_function.lambda_handler({'body': json.dumps(SAMPLE_BOM), 'requestContext': request_context, 'headers': {'accept': '*/*'}}, {})

    assert response['statusCode'] == 400
    assert response['headers']['Content-Type'] == 'application/json'
    assert response['body'] == json.dumps(
        {
        "message": "Account has not been onboarded. Please onboard it using runbook: https://paypal.atlassian.net/wiki/spaces/BTSRE/pages/939401510/Onboard+AWS+Account+to+CSoR"
        }
    )

@patch('lambdas.src.request_submitter.lambda_function.invoke_api_gateway')
@mock_aws
def test_returns_200_with_message_when_state_machine_is_successfully_triggered(mock_invoke_api_gateway):
    mock_invoke_api_gateway.side_effect = [
        {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-2"], "businessUnit": "Braintree"}]}},
        {"data": {"accounts": [{"baseline": [{"latest": {"startTime": "2023-10-01T00:00:00Z", "status": "SUCCESS", "arn": "mock-execution-arn"}}]}]}},
        {"data": ""},
    ]
    iam_client = boto3.client('iam')
    role_arn = iam_client.create_role(
        RoleName="some-role",
        AssumeRolePolicyDocument="{}"
    )['Role']['Arn']
    sf_client = boto3.client('stepfunctions', 'us-east-2')
    os.environ['STATE_MACHINE_ARN'] = sf_client.create_state_machine(
        name='testing',
        roleArn=role_arn,
        definition='some-definition'
    )['stateMachineArn']
    os.environ['SOR_ENDPOINT'] = 'https://sor.endpoint'

    request_context = build_request_context("someRequestID", "123456789", "some/userARN")
    response = lambda_function.lambda_handler({'body': json.dumps(SAMPLE_BOM), 'requestContext': request_context, 'headers': {"content-type": "application/json"}}, {})

    sf_client = boto3.client('stepfunctions', 'us-east-2')
    execution_arn = sf_client.list_executions(stateMachineArn=lambda_function.STATE_MACHINE_ARNS.get('Braintree'))['executions'][0]['executionArn']

    assert response['statusCode'] == 200
    assert response['headers']['Content-Type'] == 'application/json'
    assert response['body'] == json.dumps(
        {
            "message": f"Request successfully submitted. Please use the /status API to check the status of the execution. Execution ARN: {execution_arn}",
            "resourceId": execution_arn
        }
    )

@patch('lambdas.src.request_submitter.lambda_function.invoke_api_gateway')
@mock_aws
def test_returns_body_in_json_when_header_accept_is_application_json(mock_invoke_api_gateway):
    mock_invoke_api_gateway.side_effect = [
        {"data": {"accounts": [{"id": "081297776604", "regions": ["us-east-2"], "businessUnit": "Braintree"}]}},
        {"data": {"accounts": [{"baseline": [{"latest": {"startTime": "2023-10-01T00:00:00Z", "status": "SUCCESS", "arn": "mock-execution-arn"}}]}]}},
        {"data": ""},
    ]
    os.environ['SOR_ENDPOINT'] = 'https://sor.endpoint'

    request_context = build_request_context("someRequestID", "123456789", "some/userARN")
    response = lambda_function.lambda_handler({'body': json.dumps(SAMPLE_BOM), 'requestContext': request_context, 'headers': {'accept': 'application/json'}}, {})

    sf_client = boto3.client('stepfunctions', 'us-east-2')
    execution_arn = sf_client.list_executions(stateMachineArn=lambda_function.STATE_MACHINE_ARNS.get('Braintree'))['executions'][0]['executionArn']

    assert response['statusCode'] == 200
    assert response['headers']['Content-Type'] == 'application/json'
    assert response['body'] == json.dumps(
        {
            "message": "Request successfully submitted. Please use the /status API to check the status of the execution. Execution ARN: {}".format(execution_arn),
            "resourceId": execution_arn
        }
    )


@patch('lambdas.src.request_submitter.lambda_function.execute_sor_query')
def test_check_execution_status_no_executions(mock_execute_sor_query):
    """Test check_execution_status when no executions are found."""
    mock_execute_sor_query.return_value = {
        'data': {
            'accounts': [
                {
                    'baseline': []
                }
            ]
        }
    }

    is_in_progress, execution_arn = lambda_function.check_execution_status("1234", "us-east-2")

    assert is_in_progress is False
    assert execution_arn is None


@patch('lambdas.src.request_submitter.lambda_function.execute_sor_query')
def test_check_execution_status_in_progress(mock_execute_sor_query):
    """Test check_execution_status when an execution is in progress."""
    mock_execute_sor_query.return_value = {
        'data': {
            'accounts': [
                {
                    'baseline': [
                        {
                            'latest': {'status': 'IN_PROGRESS', 'arn': 'arn:aws:states:us-east-2:123456789012:execution:test:test-execution'}
                        }
                    ]
                }
            ]
        }
    }

    is_in_progress, execution_arn = lambda_function.check_execution_status("1234", "us-east-2")

    assert is_in_progress is True
    assert execution_arn == 'arn:aws:states:us-east-2:123456789012:execution:test:test-execution'
