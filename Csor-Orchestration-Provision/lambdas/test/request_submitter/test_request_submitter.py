import json
import os
import pytest
import boto3

from unittest.mock import patch
from moto import mock_aws
from types import SimpleNamespace

from lambdas.src.request_submitter import lambda_function

SAMPLE_BOM: dict = {
    "account": "123456789123",
    "region": "us-east-2",
    "eks": "false"
}

SAMPLE_EVENT: dict = {
    "requestContext": {
        "elb": {
            "targetGroupArn": "arn:aws:elasticloadbalancing:us-east-2:614751254790:targetgroup/tf-2023090118450943010000000a/86bcbf421ea1f4ab"
        },
        "identity": {
            "userArn": "arn:aws:sts::123456789123:assumed-role/assumed_scope_role_root/test_user",
            "accountId": "123456789123",
        },
        "requestId": "f8a8b82c-dd1e-420a-a535-3bd102f22c01"
    },
    "httpMethod": "POST",
    "path": "/",
    "queryStringParameters": {},
    "headers": {
        "accept": "application/json",
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
def state_machines():
    with mock_aws():
        client = boto3.client(service_name='stepfunctions', region_name='us-east-2')
        business_units = ["Braintree"]
        step_functions = {}
        for bu in business_units:
            state_machine = client.create_state_machine(
                name=bu,
                definition='{"StartAt": "HelloWorld", "States": {"HelloWorld": {"Type": "Pass", "Result": "Hello, World!", "End": True}}}',
                roleArn='arn:aws:iam::123456789012:role/service-role/StepFunctions-HelloWorld'
            )
            step_functions[bu] = state_machine['stateMachineArn']

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

@pytest.fixture
def account_info():
    return {
            "data": {
                "accounts": [
                    {
                        "id": "123456789123",
                        "name": "dev-test-app",
                        "accountType": "TENANT",
                        "regions": ["us-east-2"],
                        "businessUnit": "Braintree",
                        "baseline": [
                            {
                                "lastSuccess": {
                                    "status": "SUCCEEDED"
                                }
                            }
                        ]
                    }
                ]
            }
        }


@pytest.fixture()
def executions():
    return {"data": {"accounts": [{"appInfra": []}]}}

def test_parse_request_info():
    """Test we can properly parse request information"""
    request_context = {
        "identity": {"userArn": "arn:aws:sts::12345:assumed-role/my-role/davcarroll", "accountId": "123456"},
        "requestId": "1234",
    }
    request_info = lambda_function.parse_request_info(request_context)

    assert request_info['caller'] == "davcarroll"
    assert request_info['user_arn'] == "arn:aws:sts::12345:assumed-role/my-role/davcarroll"
    assert request_info['request_id'] == '1234'
    assert request_info['caller_account_id'] == "123456"


def test_invalid_account_role():
    """Test we don't let random accounts provision an account."""
    invalid_bom_event = {
        "body": json.dumps(SAMPLE_BOM),
        "requestContext": {
            "identity": {"userArn": "arn:aws:sts::12345:assumed-role/my-role/davcarroll", "accountId": "12345"},
            "requestId": "1234"
        }
    }

    response = lambda_function.lambda_handler(invalid_bom_event, {})

    assert response
    assert response['statusCode'] == 400
    assert "AWS Account ID 12345 does not match" in response['body']


def test_invalid_bom_format():
    """Test failure with invalid bom format"""
    invalid_bom_event = {
        "body": "{",
        "requestContext": {
            "identity": {"userArn": "arn:aws:sts::12345:assumed-role/my-role/davcarroll", "accountId": "12345"},
            "requestId": "1234"
        }
    }

    response = lambda_function.lambda_handler(invalid_bom_event, {})
    assert response
    assert response['statusCode'] == 400
    assert "Invalid JSON" in response['body']


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_broken_sor_communication(mock_post):
    """Test unable to communicate with sor"""
    mock_post.return_value.status_code = 500
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Encountered error when trying to validate provision request" in response["body"]
    assert "Code: 500" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_invalid_sor_communication(mock_post):
    """Test errors when communicating with SOR"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"errors": "My error"}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Encountered error when trying to validate provision request" in response["body"]
    assert "My error" in response["body"]



@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_account_does_not_exist(mock_post):
    """Test that we handle a provision request on a account that does not exist"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "The Account ID in the provision BOM does not exist in SOR" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_invalid_region(mock_post):
    """Test that we handle a provision request on a account for an invalid region"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {"accounts": [{"regions": []}]}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "cannot be provisioned in this region" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_account_not_baselined(mock_post):
    """Test that we handle a provision request on a account that has not been baselined"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {"accounts": [{"regions": ["us-east-2"], "baseline": None}]}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "The Account ID in the provision BOM has not been baselined yet" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_account_not_successfully_baselined(mock_post):
    """Test that we handle a provision request on a account that had a successful baseline"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {"accounts": [{"regions": ["us-east-2"], "baseline": [{"lastSuccess": None}]}]}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "The Account ID in the provision BOM has not been successfully baselined yet" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_account_not_successfully_baselined_null_success(mock_post):
    """Test that we handle a provision request on a account that had a successful baseline"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": {"accounts": [{"regions": ["us-east-2"], "baseline": [{"lastSuccess": "null"}]}]}}
    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "The Account ID in the provision BOM has not been successfully baselined yet" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_fail_if_active_execution(mock_post, account_info):
    """Test that we handle a provision request on a account that has an active execution running"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [
            account_info,
            {
                "data": {
                    "accounts": [
                        {
                            "appInfra": [
                                {
                                    "latest": {
                                            "arn": "1234",
                                            "status": "IN_PROGRESS"
                                     }
                                }
                            ]
                        }
                    ]
                }
            }
        ]

    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "Another execution is in progress" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_invalid_bu(mock_post, account_info, executions):
    """Test that we fail on an unrecognized BU"""
    account_info['data']['accounts'][0]['businessUnit'] = "Apollo"
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [account_info, executions]

    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 400
    assert "BU Apollo for account 123456789123 is unsupported in CSoR provision" in response["body"]


@patch('lambdas.src.request_submitter.lambda_function.requests.post')
def test_request_submitter(mock_post, account_info, executions):
    """Test we successfully submit the provision request"""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [account_info, executions, {"data": ""}]

    response = lambda_function.lambda_handler(SAMPLE_EVENT, {})

    assert response
    assert response['statusCode'] == 200
    assert 'execution:Braintree' in response['body']
    assert "Request successfully submitted." in response["body"]
