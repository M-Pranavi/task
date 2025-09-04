"""Unit tests for the 'execution-reporter' lambda code."""
import json
import os
from unittest.mock import patch, MagicMock
from pytest import fixture
import moto.sqs
import moto.stepfunctions

os.environ["SOR_ENDPOINT"] = "test_endpoint"
from lambdas.src.execution_reporter import lambda_function

REGION: str = 'us-east-2'
SAMPLE_EVENT: dict = {
    "version": "0",
    "id": "315c1398-40ff-a850-213b-158f73e60175",
    "detail-type": "Step Functions Execution Status Change",
    "source": "aws.states",
    "account": "123456789012",
    "time": "2019-02-26T19:42:21Z",
    "region": "us-east-1",
    "resources": [
        "arn:aws:states:us-east-1:123456789012:execution:state-machine-name:execution-name"
    ],
    "detail": {
        "executionArn": "arn:aws:states:us-east-1:123456789012:execution:state-machine-name:execution-name",
        "stateMachineArn": "arn:aws:states:us-east-1:123456789012:stateMachine:state-machine",
        "name": "execution-name",
        "status": "SUCCEEDED",
        "startDate": 1547148840101,
        "stopDate": 1547148840122,
        "input": "{}",
        "output": "\"Hello World!\""
    }
}

@fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Automatically mock environment variables for all tests."""
    monkeypatch.setenv("REGION", "us-east-2")
    monkeypatch.setenv("SOR_QUEUE_URL", "https://sqs.us-east-2.amazonaws.com/123456789012/test-queue")
    monkeypatch.setenv("SOR_ENDPOINT", "https://sor.endpoint")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret-key")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "test-session-token")

@fixture(name="test_queue")
def create_test_queue():
    """Create a test queue for use with moto."""
    with moto.mock_sqs():
        sqs = boto3.resource(service_name='sqs', region_name="us-east-2")
        queue_name = "test_queue.fifo"
        queue = sqs.create_queue(
            QueueName=queue_name,
            Attributes={
                "FifoQueue": "true",
                "ContentBasedDeduplication": "true"
            },
        )
        yield queue


def test_update_execution_status_sor():
    """Test the update_execution_status_sor function to update state machine execution status in SOR."""
    with patch('lambdas.src.execution_reporter.lambda_function.execute_sor_query') as mock_execute_sor_query:
        mock_execute_sor_query.return_value = {
            "data": {
                "updateStateMachineExecution": {
                    "arn": SAMPLE_EVENT['detail']['executionArn'],
                    "status": SAMPLE_EVENT['detail']['status']
                }
            }
        }
        
        response = lambda_function.update_execution_status_sor(
            execution_arn=SAMPLE_EVENT['detail']['executionArn'],
            execution_status=SAMPLE_EVENT['detail']['status']
        )
        
        assert response["data"]["updateStateMachineExecution"]["status"] == SAMPLE_EVENT['detail']['status']


@patch('requests.post')
def test_invoke_api_gateway(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"result": "test"}}
    mock_post.return_value = mock_response
    mock_post.return_value.status_code = 200

    api_url = "https://api.example.com/graphql"
    raw_query = {"query": "{ test }", "variables": {}}

    response = lambda_function.invoke_api_gateway(api_url=api_url, raw_query=raw_query)
    assert response == {"data": {"result": "test"}}
    mock_post.assert_called_once()
    headers = mock_post.call_args[1]['headers']

def test_sign_request():
    url = "https://api.example.com/graphql"
    method = "POST"
    headers = {'Content-Type': 'application/json'}
    body = json.dumps({"query": "{ test }", "variables": {}})

    signed_request = lambda_function.sign_request(url, method, headers, body)
    assert signed_request.method == method
    assert signed_request.url == url
    assert signed_request.headers["Content-Type"] == headers["Content-Type"]

def test_execute_sor_query():
    with patch('lambdas.src.execution_reporter.lambda_function.invoke_api_gateway') as mock_invoke_api_gateway:
        mock_invoke_api_gateway.return_value = {"data": {"result": "test"}}

        query = "query { test }"
        variables = {"var1": "value1"}
        
            # Set environment variable for the test
        os.environ['SOR_ENDPOINT'] = 'https://sor.endpoint'

        response = lambda_function.execute_sor_query(query, variables)
        assert response == {"data": {"result": "test"}}
        mock_invoke_api_gateway.assert_called_once()
