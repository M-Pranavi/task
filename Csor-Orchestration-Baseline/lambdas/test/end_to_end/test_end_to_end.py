import json
import os
import time
import argparse

import boto3
import requests
import urllib3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

urllib3.disable_warnings()

# Create a single session for connection reuse
requests_session = requests.Session()
requests_session.verify = False


def make_request(method, url, data, role, region):
    awsrequest = AWSRequest(
        method=method,
        url=url,
        data=json.dumps(data),
    )

    session = boto3.Session(region_name=region)

    sts_client = boto3.client('sts')
    response = sts_client.assume_role(RoleArn=role, RoleSessionName=f"e2e_baseline")
    session = boto3.Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken'],
        region_name=region
    )

    SigV4Auth(session.get_credentials(), 'execute-api', session.region_name).add_auth(awsrequest)
    response = requests_session.request(method=method,
                                url=url,
                                data=json.dumps(data),
                                headers=awsrequest.headers,
                                timeout=10)
    if response.status_code != 200:
        assert False, f"Request failed with status code {response.status_code}. Response: {response.text}"
    return response


def get_fcd(environment_json):
    query = """
        query {
            fcd {
                configurationDocument
                createdAt
            }
        }
    """
    raw_query = {
        "query": query,
        "variables": {}
    }
    response = make_request(
        'POST', 
        environment_json['sor_url'], 
        raw_query,
        environment_json["orchestration_aws_assume_role"],
        environment_json["sor_aws_region"]
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Request failed with status code {response.status_code}. Response: {response.text}"
        )
    return json.loads(response.content.decode('utf-8'))['data']['fcd']['configurationDocument']


def test_e2e_baseline(environment_json):
    orchestration_url = environment_json['orchestration_url']
    data = get_fcd(environment_json)
    data["account"] = environment_json['e2e_aws_account_num']
    data["environment"] = environment_json['e2e_aws_account_env']
    data["name"] = environment_json['e2e_aws_account_name']
    data["region"] = environment_json.get("region")

    response = make_request("POST", orchestration_url, data,
                            environment_json["orchestration_aws_assume_role"],
                            environment_json["orchestration_aws_region"])

    execution_arn = json.loads(response.content.decode("utf-8"))['resourceId']
    print("Exec arn: ", execution_arn)
    t_end = time.time() + 60 * environment_json["max_wait_time_in_minutes"]
    sor_response = ""
    while time.time() < t_end:
        query = """
            query {
                statusByExecution(executionArn: "%s") {
                    arn
                    stateMachineType
                    status
                    startTime
                    configurationDocument
                    deployers {
                      name
                      status
                      version
                      outputs
                    }
                }
            }
        """ % execution_arn

        raw_query = {
            "query": query,
            "variables": {}
        }
        sor_url = environment_json['sor_url']

        response = make_request("POST", sor_url, raw_query,
                                environment_json["orchestration_aws_assume_role"],
                                environment_json["sor_aws_region"])

        sor_response = json.loads(response.content.decode('utf-8'))
        if 'errors' in sor_response:
            assert False, f"Graphql returned errors: {sor_response}"

        execution_status = sor_response['data']['statusByExecution']['status']
        if execution_status == "SUCCEEDED":
            print(f'Baseline completed successfully for execution %s' % execution_arn)
            assert True
            return
        elif execution_status == "FAILED":
            assert False, f'Baseline execution failed to complete successfully %s' % sor_response
        elif execution_status == "ABORTED":
            assert False, f'Baseline execution aborted before completion %s' % sor_response
        elif execution_status == "TIMED_OUT":
            assert False, f'Baseline execution timed out before completion %s' % sor_response
        else:
            print(f"Baseline still running. Current status: %s" % execution_status)
        time.sleep(15)
    assert False, f"State machine status did not transition to SUCCEEDED in %s minutes. Last SOR response: %s" % (environment_json["max_wait_time_in_minutes"], sor_response)

def main():
    parser = argparse.ArgumentParser(description='Run end-to-end tests.')
    parser.add_argument('--region', required=True, help='The AWS region to use.')
    args = parser.parse_args()

    with open(os.getenv('ENVIRONMENT_JSON')) as json_file:
        environment_json = json.load(json_file)

    environment_json['region'] = args.region

    test_e2e_baseline(environment_json)


if __name__ == "__main__":
    main()
    
