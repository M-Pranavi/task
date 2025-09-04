
"""Unit tests for the 'execution-reporter' lambda code."""

import json
import os
from unittest.mock import patch, MagicMock
from pytest import fixture
from ...src.execution_reporter import lambda_function

def test_execute_sor_query():
    with patch('lambdas.src.execution_reporter.lambda_function.invoke_api_gateway') as mock_invoke_api_gateway:
        mock_invoke_api_gateway.return_value = {"data": {"result": "test"}}
        os.environ['SOR_ENDPOINT'] = 'https://sor_endpoint'
        query = "query { test }"
        variables = {"var1": "value1"}

        response = lambda_function.execute_sor_query(query, variables)
        assert response == {"data": {"result": "test"}}
