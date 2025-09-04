"""Unit tests for the 'task-definition-creator' lambda code."""

import json
import boto3
import botocore
import pytest
import copy
import time
import asyncio

from unittest.mock import patch, MagicMock
from moto import mock_dynamodb, mock_ecs

from lambdas.src.task_definitions_creator import lambda_function

DYNAMODB_TABLE_NAME = "test-table"
ECR_REPOSITORY = "1234.ecr.repo"

@pytest.fixture
def sample_event():
    return {"input": {
        "test_deployer": "1.0.0",
        "network_deployer": "1.0.0",
        "stackset_deployer": "1.0.0"
    }}

@pytest.fixture
def sample_new_event():
    return {"input": {
        "test_deployer": "1.0.1",
        "network_deployer": "1.0.1",
        "stackset_deployer": "1.0.1"
    }}

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Auto set up env vars"""
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", DYNAMODB_TABLE_NAME)
    monkeypatch.setenv("ECR_REPOSITORY", ECR_REPOSITORY)

def create_test_dynamodb():
    """Create a test dynamodb table."""
    client = boto3.client('dynamodb', region_name='us-east-2')
    client.create_table(
        AttributeDefinitions=[
            {"AttributeName": "Name_Version", "AttributeType": "S"}
        ],
        TableName=DYNAMODB_TABLE_NAME,
        KeySchema=[
            {"AttributeName": "Name_Version", "KeyType": "HASH"}
        ],
        BillingMode="PAY_PER_REQUEST"
    )

def setup_test_env(event):
    """Setup the test environment."""
    create_test_dynamodb()

    ecs_client = boto3.client('ecs', region_name='us-east-2')
    table = boto3.resource('dynamodb', region_name='us-east-2').Table(DYNAMODB_TABLE_NAME)
    for name, version in event['input'].items():

        ecs_client.register_task_definition(
            family = name + "_baseline",
            containerDefinitions=[{"image": f"{ECR_REPOSITORY}/{name}:{version}"}],
            cpu="1024",
            memory="3072",
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            executionRoleArn="role-arn-1234",
            taskRoleArn="task-role-arn-1234",
            tags=[{"key": "test", "value": "true"}],
            volumes=[{"name": "test-volume"}]
        )

        test_item = {
            "Name_Version": f"{name}:{version}",
            "Lock_Status": "REGISTERED",
            "TaskDefinitionArn": f"arn-{name}-{version}"
        }
        table.put_item(Item=test_item)

def test_create_ecs_client():
    """Test that we return a boto3 ecs client."""
    client = lambda_function.__create_ecs_client('us-east-2')
    assert client

def test_get_dynamodb_table():
    """Test that we return a boto3 client for dynamodb."""
    client = lambda_function.__get_dynamodb_table(DYNAMODB_TABLE_NAME, 'us-east-2')
    assert client

@mock_dynamodb
@mock_ecs
def test_arn_exists(sample_event):
    """Test that we pass in an existing task definition"""
    setup_test_env(sample_event)
    new_bom = lambda_function.lambda_handler(copy.deepcopy(sample_event), {})
    assert new_bom

    for deployer, version in sample_event['input'].items():
        assert new_bom[deployer] == f"arn-{deployer}-{version}"

@mock_dynamodb
@mock_ecs
def test_new_arns(sample_event, sample_new_event):
    """Test that we create new task definitions if they do not exist."""
    setup_test_env(sample_event)
    new_bom = lambda_function.lambda_handler(copy.deepcopy(sample_new_event), {})
    assert new_bom

    for deployer, version in sample_event['input'].items():
        assert new_bom[deployer] == f"arn:aws:ecs:us-east-2:123456789012:task-definition/{deployer}_baseline:2"

    ecs_client = boto3.client('ecs', region_name='us-east-2')
    task_defs = ecs_client.list_task_definitions(status='ACTIVE')
    assert len(task_defs['taskDefinitionArns']) == len(sample_event['input'])*2

    task_def = ecs_client.describe_task_definition(
            taskDefinition=f"arn:aws:ecs:us-east-2:123456789012:task-definition/test_deployer_baseline:2"
    )

    assert task_def['taskDefinition']['containerDefinitions'][0]['image'] == f"{ECR_REPOSITORY}/test_deployer:{sample_new_event['input']['test_deployer']}"

    table = boto3.resource('dynamodb', region_name='us-east-2').Table(DYNAMODB_TABLE_NAME)

    for deployer, version in sample_new_event['input'].items():
        item = table.get_item(Key={'Name_Version': f"{deployer}:{sample_new_event['input'][deployer]}"})['Item']
        assert item['Lock_Status'] == 'REGISTERED'
        assert item['TaskDefinitionArn']


@patch('lambdas.src.task_definitions_creator.lambda_function.sleep', return_value=None)
@mock_dynamodb
@mock_ecs
def test_fails_when_locked(sample_event, sample_new_event):
    """Test that we successfully fail if a dynamodb item remains locked"""
    setup_test_env(sample_event)
    table = boto3.resource('dynamodb', region_name='us-east-2').Table(DYNAMODB_TABLE_NAME)
    item = {
        "Name_Version": f"test_deployer:{sample_new_event['input']['test_deployer']}",
        "Lock_Status": "LOCKED"
    }
    table.put_item(Item=item)

    with pytest.raises(botocore.exceptions.ClientError):
        new_bom = lambda_function.lambda_handler(copy.deepcopy(sample_new_event), {})

async def release_lock(sample_new_event, table):
    """Async function to release lock after some time"""
    time.sleep(5)
    table.update_item(
            Key={"Name_Version": f"test_deployer:{sample_new_event['input']['test_deployer']}"},
            UpdateExpression='SET TaskDefinitionArn = :arn, Lock_Status = :status',
            ExpressionAttributeValues={
                ':status': 'REGISTERED',
                ':arn': 'locked-status-arn'
            }
    )

@mock_dynamodb
@mock_ecs
def test_succeeds_when_lock_is_released(sample_event, sample_new_event):
    """Test that is wait for the lock to be released and succeeds if it is"""
    setup_test_env(sample_event)
    table = boto3.resource('dynamodb', region_name='us-east-2').Table(DYNAMODB_TABLE_NAME)
    item = {
        "Name_Version": f"test_deployer:{sample_new_event['input']['test_deployer']}",
        "Lock_Status": "LOCKED"
    }
    table.put_item(Item=item)

    asyncio.run(release_lock(sample_new_event, table))
    new_bom = lambda_function.lambda_handler(copy.deepcopy(sample_new_event), {})
    assert new_bom

    assert new_bom['test_deployer'] == 'locked-status-arn'
