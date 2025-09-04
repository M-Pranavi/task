import os
import json
import hashlib
import subprocess
import shutil
import tempfile
import atexit
import glob
import argparse
import traceback
import sys
import boto3
from botocore.exceptions import ClientError

LAMBDAS_DIR = "lambdas/src"
S3_HASH_FILE = "check_lambda_changes/lambda-hashes.json"
FIXED_TIMESTAMP = "202001010000"
BUILD_DIR = "build"
ORCHESTRATION_REGION="us-east-2"

def normalize_timestamps(directory):
    """Set all files to a fixed timestamp for deterministic ZIP creation"""
    cmd = f"find {directory} -type f -exec touch -t {FIXED_TIMESTAMP} {{}} \\;"
    subprocess.run(cmd, shell=True, check=True)

def get_lambda_hash(project):
    """Calculate hash for a Lambda project"""
    source_dir = os.path.join(LAMBDAS_DIR, project)
    with tempfile.NamedTemporaryFile(suffix='.zip') as temp_zip:
        output_zip_abs = os.path.abspath(temp_zip.name)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_source = os.path.join(temp_dir, os.path.basename(source_dir))
            shutil.copytree(source_dir, temp_source)
            normalize_timestamps(temp_source)
            
            current_dir = os.getcwd()
            os.chdir(temp_dir)
            cmd = f"find {os.path.basename(source_dir)} -type f | sort | zip -X -@ temp_lambda.zip > /dev/null 2>&1"
            subprocess.run(cmd, shell=True, check=True)
            os.chdir(current_dir)
            
            os.makedirs(os.path.dirname(output_zip_abs), exist_ok=True)
            shutil.move(os.path.join(temp_dir, "temp_lambda.zip"), output_zip_abs)
        
        sha1_hash = hashlib.sha1()
        with open(temp_zip.name, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha1_hash.update(chunk)
        return sha1_hash.hexdigest()

def cleanup_zip_files():
    """Remove temporary ZIP files created during processing"""
    zip_files = glob.glob(f"{BUILD_DIR}/*.zip")
    for zip_file in zip_files:
        try:
            os.remove(zip_file)
        except Exception:
            pass

def get_available_lambdas():
    """Get a list of all Lambda function names"""
    return [d for d in os.listdir(LAMBDAS_DIR) 
            if os.path.isdir(os.path.join(LAMBDAS_DIR, d)) and d != "__pycache__"]

def assume_role(env=None):
    """Assume AWS role for the specified account and environment"""
    if env.startswith("tenant-"):
        env_name = env
    else:
        env_name = f"internal-{env}" if not env.startswith("internal-") else env
    
    json_file = f"environments/{env_name}.json"
    
    try:
        with open(json_file, 'r') as f:
            env_config = json.load(f)
        
        role_arn = env_config.get("orchestration_aws_assume_role")
        
        if not role_arn:
            raise ValueError(f"Role ARN not found in {json_file}")
            
    except FileNotFoundError:
        raise FileNotFoundError(f"Environment file not found: {json_file}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in environment file: {json_file}")
    except Exception as e:
        raise RuntimeError(f"Error reading {json_file}: {str(e)}")
    
    print(f"Assuming role: {role_arn}")
    
    sts_client = boto3.client('sts', region_name=ORCHESTRATION_REGION)
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName='LambdaChangeDetection'
    )
    
    credentials = response['Credentials']
    
    return boto3.client(
        's3',
        region_name=ORCHESTRATION_REGION,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )

def get_hashes_from_s3(s3_client, bucket):
    """Retrieve stored Lambda hash values from S3"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=S3_HASH_FILE)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except ClientError as e:
        if e.response['Error']['Code'] in ['NoSuchKey', 'NoSuchBucket']:
            return {}
        raise
    except json.JSONDecodeError:
        return {}

def update_hashes_in_s3(s3_client, bucket, hashes):
    """Store updated Lambda hash values in S3"""
    s3_client.put_object(
        Bucket=bucket,
        Key=S3_HASH_FILE,
        Body=json.dumps(hashes, indent=2),
        ContentType='application/json'
    )

def detect_lambda_changes(account_id=None, env=None):
    """Detect which Lambda functions have changed"""
    if account_id is None or env is None:
        return None
        
    s3_client = assume_role(env)
    bucket = f"csor-baseline-{account_id}-lambda-artifacts"
    
    existing_hashes = get_hashes_from_s3(s3_client, bucket)
    lambda_projects = get_available_lambdas()
    
    changed_lambdas = []
    
    for project in lambda_projects:
        sha1sum = get_lambda_hash(project)
        existing_hash = existing_hashes.get(project)
        
        if existing_hash is None or existing_hash != sha1sum:
            changed_lambdas.append(project)
    
    return changed_lambdas

def update_lambda_hashes(account_id=None, env=None):
    """Update hashes in S3 after successful Lambda upload"""
    if account_id is None or env is None:
        return False
        
    s3_client = assume_role(env)
    bucket = f"csor-baseline-{account_id}-lambda-artifacts"
    
    existing_hashes = get_hashes_from_s3(s3_client, bucket)
    updated_hashes = existing_hashes.copy()
    
    lambda_projects = get_available_lambdas()
    
    for project in lambda_projects:
        sha1sum = get_lambda_hash(project)
        updated_hashes[project] = sha1sum
    
    update_hashes_in_s3(s3_client, bucket, updated_hashes)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Lambda functions for changes using deterministic ZIP hashing.")
    parser.add_argument("--env", type=str, required=True, help="Environment name for output formatting")
    parser.add_argument("--account", type=str, required=True, help="AWS account ID for S3 bucket")
    parser.add_argument("--update-hashes", action="store_true", help="Update hashes in S3 for all Lambda functions")
    
    args = parser.parse_args()
    
    atexit.register(cleanup_zip_files)
    
    try:
        if args.update_hashes:
            success = update_lambda_hashes(args.account, args.env)
            sys.exit(0 if success else 1)
        
        changed_lambdas = detect_lambda_changes(args.account, args.env)

        if changed_lambdas is not None:
            env_name = args.env.upper()
            if changed_lambdas:
                print(f"CHANGED_LAMBDAS_{env_name}={' '.join(changed_lambdas)}")
            sys.exit(0)
        else:
            print("ERROR: Failed to detect Lambda changes - check parameters and permissions")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
