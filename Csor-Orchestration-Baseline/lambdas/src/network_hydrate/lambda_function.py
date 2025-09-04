"""Custom ETL process to hydrate CSOR DB from S3 object updates."""

import logging
import json
import os
from os import getenv
from typing import Any
import urllib.parse
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session

# Set up logging
LOGGING_LEVEL = getenv("LOGGING_LEVEL", "INFO")
VALID_LOGGING_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

LOGGER = logging.getLogger()
if LOGGING_LEVEL in VALID_LOGGING_LEVELS and LOGGER.handlers:
    LOGGER.setLevel(LOGGING_LEVEL)
elif LOGGING_LEVEL not in VALID_LOGGING_LEVELS and LOGGER.handlers:
    LOGGER.setLevel(level=logging.DEBUG)
elif LOGGING_LEVEL in VALID_LOGGING_LEVELS:
    logging.basicConfig(level=LOGGING_LEVEL)
else:
    logging.basicConfig(level=logging.DEBUG)
LOGGER.debug("Logging Level: %s", LOGGER.getEffectiveLevel())


def __get_env_variable(var_name, default=None):
    """Retrieve an environment variable with an optional default."""
    return os.getenv(var_name, default)


def get_object_contents(bucket, key, bucket_region):
    """
    Read in s3 object json document
    """

    client = boto3.client("s3", region_name=bucket_region)

    try:
        response = client.get_object(Bucket=bucket, Key=key)
        json_blob = json.loads(response["Body"].read())
    except Exception as e:
        LOGGER.exception(e)
        LOGGER.exception(
            "Error getting object %s from bucket %s.",
            key,
            bucket,
        )
        raise e

    return json_blob


def sign_request(url, method, headers, body):
    """Sign the request using SigV4"""
    session = get_session()
    credentials = session.get_credentials().get_frozen_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, "execute-api", os.getenv("REGION")).add_auth(request)
    return request


def invoke_api_gateway(api_url, raw_query=None):
    """Invoke API Gateway with SigV4 signing"""
    headers = {"Content-Type": "application/json"}
    body = json.dumps(raw_query)
    signed_request = sign_request(api_url, "POST", headers, body)
    response = requests.post(
        api_url,
        data=signed_request.body,
        headers=dict(signed_request.headers.items()),
        timeout=3,
    )

    return response.json()


def execute_sor_query(query: str, variables: dict = None) -> dict:
    """Invoke the GraphQL query via API Gateway"""
    raw_query = {"query": query, "variables": variables or {}}
    api_url = os.getenv("SOR_ENDPOINT")
    LOGGER.info("Invoking mutation call on SoR url %s", api_url)
    response = invoke_api_gateway(api_url=api_url, raw_query=raw_query)
    return response


def mutate_networkfoundation_data(payload: dict[str, Any]) -> dict:
    """Mutate foundation data in System of Record"""
    foundation_query: str = (
        """
    mutation (
        $accountId: String!, 
        $region: Region!, 
        $vpcId: String!, 
        $publicSubnetIds: [String!], 
        $privateSubnetIds: [String!], 
        $privateEksSubnetIds: [String!], 
        $vpcCidr: String!, 
        $vpcCidrAllocation: [String!], 
        $privateZoneId: String!, 
        $dimensionPrivateZoneId: String!, 
        $braintreeApiComZoneId: String!, 
        $fdfgSftpWhitelistCidrs: [String!], 
        $vpcDnsAddr: String!, 
        $availabilityZonesDsv: String!,
        $asmEndpointIps: [String!], 
        $autoscalingEndpointIps: [String!], 
        $cloudformationEndpointIps: [String!], 
        $dynamodbEndpointCidrBlocks: [String!], 
        $ec2EndpointIps: [String!], 
        $elasticloadbalancingEndpointIps: [String!], 
        $s3EndpointCidrBlocks: [String!], 
        $stsEndpointIps: [String!], 
        $logsEndpointIps: [String!], 
        $efsEndpointIps: [String!], 
        $sqsEndpointIps: [String!],
        $publicAccessCidrs: [String!],
    ){
        setNetworkFoundation(accountId: $accountId, region: $region, vpcId: $vpcId, publicSubnetIds: $publicSubnetIds, privateSubnetIds: $privateSubnetIds, privateEksSubnetIds: $privateEksSubnetIds, vpcCidr: $vpcCidr, vpcCidrAllocation: $vpcCidrAllocation, privateZoneId: $privateZoneId, dimensionPrivateZoneId: $dimensionPrivateZoneId, braintreeApiComZoneId: $braintreeApiComZoneId, fdfgSftpWhitelistCidrs: $fdfgSftpWhitelistCidrs, vpcDnsAddr: $vpcDnsAddr, availabilityZonesDsv: $availabilityZonesDsv, asmEndpointIps: $asmEndpointIps, autoscalingEndpointIps: $autoscalingEndpointIps, cloudformationEndpointIps: $cloudformationEndpointIps, dynamodbEndpointCidrBlocks: $dynamodbEndpointCidrBlocks, ec2EndpointIps: $ec2EndpointIps, elasticloadbalancingEndpointIps: $elasticloadbalancingEndpointIps, s3EndpointCidrBlocks: $s3EndpointCidrBlocks, stsEndpointIps: $stsEndpointIps, logsEndpointIps: $logsEndpointIps, efsEndpointIps: $efsEndpointIps, sqsEndpointIps: $sqsEndpointIps, publicAccessCidrs: $publicAccessCidrs) {
            network {
                accountId
                region
                vpcId
                publicSubnetIds
                privateSubnetIds
                privateEksSubnetIds
                vpcCidr
                vpcCidrAllocation
                privateZoneId
                dimensionPrivateZoneId
                braintreeApiComZoneId
                fdfgSftpWhitelistCidrs
                vpcDnsAddr
                availabilityZonesDsv
                asmEndpointIps
                autoscalingEndpointIps 
                cloudformationEndpointIps
                dynamodbEndpointCidrBlocks
                ec2EndpointIps
                elasticloadbalancingEndpointIps
                s3EndpointCidrBlocks
                stsEndpointIps
                logsEndpointIps
                efsEndpointIps
                sqsEndpointIps
                publicAccessCidrs
            }
        }
    }
    """
    )

    variables: dict[str, Any] = {
        "region": payload["region"],
        "accountId": payload["accountId"],
        "vpcId": payload["vpcId"],
        "publicSubnetIds": payload["publicSubnetIds"],
        "privateSubnetIds": payload["privateSubnetIds"],
        "privateEksSubnetIds": payload["privateEksSubnetIds"],
        "vpcCidr": payload["vpcCidr"],
        "vpcCidrAllocation": payload["vpcCidrAllocation"],
        "privateZoneId": payload["privateZoneId"],
        "dimensionPrivateZoneId": payload["dimensionPrivateZoneId"],
        "braintreeApiComZoneId": payload["braintreeApiComZoneId"],
        "fdfgSftpWhitelistCidrs": payload["fdfgSftpWhitelistCidrs"],
        "vpcDnsAddr": payload["vpcDnsAddr"],
        "availabilityZonesDsv": payload["availabilityZonesDsv"],
        "asmEndpointIps": payload["asmEndpointIps"],
        "autoscalingEndpointIps": payload["autoscalingEndpointIps"],
        "cloudformationEndpointIps": payload["cloudformationEndpointIps"],
        "dynamodbEndpointCidrBlocks": payload["dynamodbEndpointCidrBlocks"],
        "ec2EndpointIps": payload["ec2EndpointIps"],
        "elasticloadbalancingEndpointIps": payload["elasticloadbalancingEndpointIps"],
        "s3EndpointCidrBlocks": payload["s3EndpointCidrBlocks"],
        "stsEndpointIps": payload["stsEndpointIps"],
        "logsEndpointIps": payload["logsEndpointIps"],
        "efsEndpointIps": payload["efsEndpointIps"],
        "sqsEndpointIps": payload["sqsEndpointIps"],
        "publicAccessCidrs": payload["publicAccessCidrs"],
    }

    response = execute_sor_query(foundation_query, variables)
    LOGGER.info("Network Foundation mutation query response: %s", response)
    return response


def lambda_handler(event: dict, context: dict) -> dict:
    """Entrypoint for AWS Lambda. Main Function."""
    LOGGER.info("Event received: %s", event)

    cosmos_account_numbers = {
        "data-production": "140583960461",
        "data-staging": "421799854738",
        "dev": "782759316251",
        "qa": "782759316251",
        "jenkins-prod": "018711540077",
        "jenkins-sand": "648372896714",
        "prod": "123910207971",
        "sand": "303892774901",
        "splunk": "195526673873",
    }

    # Get payload from s3 object
    s3_message = json.loads(event["Records"][0]["Sns"]["Message"])
    LOGGER.info("s3_message: %s", s3_message)
    bucket_name = s3_message["Records"][0]["s3"]["bucket"]["name"]
    LOGGER.info("bucket_name: %s", bucket_name)
    key = urllib.parse.unquote_plus(
        s3_message["Records"][0]["s3"]["object"]["key"], encoding="utf-8"
    )
    LOGGER.info("key: %s", key)
    bucket_region = s3_message["Records"][0]["awsRegion"]

    if not __get_env_variable("SOR_ENDPOINT"):
        raise KeyError("No SoR endpoint set")

    object_contents = get_object_contents(bucket_name, key, bucket_region)
    dimension_terraform_outputs = object_contents["outputs"]
    LOGGER.info("S3 object contents: %s", dimension_terraform_outputs)

    dimension_region = key.split("/", 3)[1]
    dimension = dimension_region.split("-")[0]
    region = dimension_region.split(dimension + "-")[1]

    bastion_whitelist_cidrs_dsv_string = dimension_terraform_outputs["bastion_whitelist_cidrs_dsv"]["value"]
    bastion_whitelist_cidrs_dsv = bastion_whitelist_cidrs_dsv_string.split(",")
    kube_api_additional_whitelist_cidrs  =  os.getenv("KUBE_API_ADDITIONAL_WHITELIST_CIDRS","").split(",")
    public_access_cidrs = bastion_whitelist_cidrs_dsv + kube_api_additional_whitelist_cidrs
    LOGGER.info("Public Access Cidrs list: %s", public_access_cidrs)
    
    # All parameters below are read from the dimension-terraform tfstate s3 object that triggered lambda invocation
    payload = {
        "region": region,
        "accountId": cosmos_account_numbers[dimension],
        "vpcId": dimension_terraform_outputs["vpc_id"]["value"],
        "publicSubnetIds": dimension_terraform_outputs["public_subnet_ids"]["value"],
        "privateSubnetIds": dimension_terraform_outputs["private_subnet_ids"]["value"],
        "privateEksSubnetIds": dimension_terraform_outputs["private_eks_subnet_ids"][
            "value"
        ],
        "vpcCidr": dimension_terraform_outputs["vpc_cidr"]["value"],
        "vpcCidrAllocation": dimension_terraform_outputs["vpc_cidr_allocation"][
            "value"
        ],
        "privateZoneId": dimension_terraform_outputs["private_zone_id"]["value"],
        "dimensionPrivateZoneId": dimension_terraform_outputs[
            "dimension_private_zone_id"
        ]["value"],
        "braintreeApiComZoneId": dimension_terraform_outputs[
            "braintree_api_com_zone_id"
        ]["value"],
        "fdfgSftpWhitelistCidrs": dimension_terraform_outputs[
            "fdfg_sftp_whitelist_cidrs"
        ]["value"],
        "vpcDnsAddr": dimension_terraform_outputs["vpc_dns_addr"]["value"],
        "availabilityZonesDsv": dimension_terraform_outputs["availability_zones_dsv"][
            "value"
        ],
        "asmEndpointIps": dimension_terraform_outputs["asm_endpoint_ips"]["value"],
        "autoscalingEndpointIps": dimension_terraform_outputs[
            "autoscaling_endpoint_ips"
        ]["value"],
        "cloudformationEndpointIps": dimension_terraform_outputs[
            "cloudformation_endpoint_ips"
        ]["value"],
        "dynamodbEndpointCidrBlocks": dimension_terraform_outputs[
            "dynamodb_endpoint_cidr_blocks"
        ]["value"],
        "ec2EndpointIps": dimension_terraform_outputs["ec2_endpoint_ips"]["value"],
        "elasticloadbalancingEndpointIps": dimension_terraform_outputs[
            "elasticloadbalancing_endpoint_ips"
        ]["value"],
        "s3EndpointCidrBlocks": dimension_terraform_outputs["s3_endpoint_cidr_blocks"][
            "value"
        ],
        "stsEndpointIps": dimension_terraform_outputs["sts_endpoint_ips"]["value"],
        "logsEndpointIps": dimension_terraform_outputs["logs_endpoint_ips"]["value"],
        "efsEndpointIps": dimension_terraform_outputs["efs_endpoint_ips"]["value"],
        "sqsEndpointIps": dimension_terraform_outputs["sqs_endpoint_ips"]["value"],
        "publicAccessCidrs": public_access_cidrs,
    }

    mutation_response = mutate_networkfoundation_data(payload=payload)
    LOGGER.info("Mutation response: %s", mutation_response)


if __name__ == "__main__":
    import sys

    lambda_handler(event={"event": "stuff"}, context={"foo": "bar"})
    sys.exit()
