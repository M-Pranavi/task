"""Task definition creator lambda to create/set ECS task definition for deployer version"""

import json
import boto3
from botocore.exceptions import ClientError
from time import sleep
import logging
import os

# Set up logging
LOGGER = logging.getLogger()
if len(LOGGER.handlers) > 0:
    LOGGER.setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)


def __create_ecs_client(region):
    """Create a boto3 ECS Client."""
    return boto3.client('ecs', region_name=region)


def __get_dynamodb_table(table_name, region):
    """Create a boto3 DynamoDB resource for the table."""
    return boto3.resource('dynamodb', region_name=region).Table(table_name)


def lambda_handler(event, context):
    """Entrypoint for AWS Lambda. Main Function."""
    LOGGER.info(f"Input BOM received: {event}")
    bom = event["input"]

    dynamodb_table_name= str(os.getenv('DYNAMODB_TABLE_NAME'))
    ecr_repository= str(os.getenv('ECR_REPOSITORY'))
    region = str(os.getenv('REGION', 'us-east-2'))

    ecs_client=__create_ecs_client(region)

    table=__get_dynamodb_table(dynamodb_table_name, region)

    deployer_versions = {key: value for key, value in bom.items() if "deployer" in key}

    for name, version in deployer_versions.items():
        task_family = name + "_baseline"

        LOGGER.info(f"Finding/Creating task definition for task family {task_family}")

        try:
            name_version = name + ":" + version
            # Check if the version already has a task definition in DynamoDB
            response = table.get_item(Key={'Name_Version': name_version})
            if 'Item' in response and response['Item']['Lock_Status'] == 'REGISTERED':
                #Set the task_definition_arn here and continue to the next deployer
                bom[name] = response['Item']['TaskDefinitionArn']
                LOGGER.info(f"Task definition {bom[name]} found for deployer version: {name_version}")
                continue

            LOGGER.info(f"Creating new task definition for deployer version: {name_version}")
            # Attempt to acquire the lock by creating an item in DynamoDB
            table.put_item(
                Item={'Name_Version': name_version, 'Lock_Status': 'LOCKED'},
                ConditionExpression='attribute_not_exists(Name_Version)'
            )

            # Describe the current task definition to use as a base
            task_definitions = ecs_client.list_task_definitions(
                familyPrefix=task_family,
                status='ACTIVE',
                sort='DESC'
            )
            latest_task_definition_arn = task_definitions['taskDefinitionArns'][0]
            LOGGER.info(f"Latest task definition ARN: {latest_task_definition_arn}")
            response = ecs_client.describe_task_definition(
                taskDefinition=latest_task_definition_arn,
                include=[
                    'TAGS',
                ]
            )

            container_definitions = response['taskDefinition']['containerDefinitions']
            for container in container_definitions:
                if "falcon" not in container["image"]:
                    if name == "base_deployer":
                        container['image'] = f"{ecr_repository}/baseline_base_deployer:{version}"
                    else:
                        container['image'] = f"{ecr_repository}/{name_version}"

            # Register a new task definition with the updated image
            new_task_definition = ecs_client.register_task_definition(
                family=task_family,
                containerDefinitions=container_definitions,
                cpu=response['taskDefinition']['cpu'],
                memory=response['taskDefinition']['memory'],
                networkMode=response['taskDefinition']['networkMode'],
                requiresCompatibilities=response['taskDefinition']['requiresCompatibilities'],
                executionRoleArn=response['taskDefinition']['executionRoleArn'],
                taskRoleArn=response['taskDefinition']['taskRoleArn'],
                volumes=response['taskDefinition']['volumes'],
                tags=response['tags']
            )

            # Update DynamoDB with the new task definition Arn
            table.update_item(
                Key={'Name_Version': name_version},
                UpdateExpression='SET TaskDefinitionArn = :arn, Lock_Status = :status',
                ExpressionAttributeValues={
                    ':arn': new_task_definition['taskDefinition']['taskDefinitionArn'],
                    ':status': 'REGISTERED'
                }
            )

            bom[name] = new_task_definition['taskDefinition']['taskDefinitionArn']

            LOGGER.info(f"Task definition {bom[name]} successfully created for deployer version: {name_version}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                # If the item already exists, another process has already registered/locked the task definition
                LOGGER.info(f"Task definition LOCKED in DynamoDB for deployer version: {name_version}")
                response = table.get_item(Key={'Name_Version': name_version})
                if response['Item']['Lock_Status'] == 'REGISTERED':
                    bom[name] = response['Item']['TaskDefinitionArn']
                    LOGGER.info(f"Task definition {bom[name]} found for deployer version: {name_version}")
                else:
                    LOGGER.info(f"Sleeping for 10 seconds, waiting for task definition for deployer_version {name_version} to be registered by another process")
                    sleep(10)
                    response = table.get_item(Key={'Name_Version': name_version})
                    if response['Item']['Lock_Status'] == 'REGISTERED':
                        bom[name] = response['Item']['TaskDefinitionArn']
                        LOGGER.info(f"Task definition {bom[name]} found for deployer version: {name_version}")
                    else:
                        LOGGER.info(f"Error: Deployer {name_version} LOCKED for more than 10 seconds, exiting")
                        raise e
            else:
                raise e

    LOGGER.info(f"New BOM after converting deployer versions to TaskDefinitionArns: {bom}")
    return bom
