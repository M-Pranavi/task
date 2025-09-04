import boto3
import argparse
from datetime import datetime

# AWS region (modify if needed)
AWS_REGION = "us-east-2"

# Mapping of environment to AWS account numbers
ENV_ACCOUNT_MAP = {
    "internal-dev": "614751254790",
    "internal-qa": "381492044061",
    "dev": "339712721196",
    "qa": "891377279854",
    "sand": "339713027185",
    "prod": "339712719475"
}

def construct_step_function_arn(environment, step_function_name):
    """Construct the Step Function ARN based on environment and name."""
    if environment not in ENV_ACCOUNT_MAP:
        raise ValueError(f"Invalid environment '{environment}'. Choose from: {list(ENV_ACCOUNT_MAP.keys())}")
    
    account_id = ENV_ACCOUNT_MAP[environment]
    return f"arn:aws:states:{AWS_REGION}:{account_id}:stateMachine:{step_function_name}"

def get_last_executions(client, step_function_arn, max_results=50):
    """Get the last `max_results` executions of the step function."""
    response = client.list_executions(
        stateMachineArn=step_function_arn,
        maxResults=max_results,
        statusFilter="SUCCEEDED"
    )
    return [exe['executionArn'] for exe in response.get('executions', [])]

def get_task_durations(client, execution_arn, task_name):
    """Get start and end time of a specific task within an execution."""
    response = client.get_execution_history(
        executionArn=execution_arn,
        reverseOrder=False  # Process in chronological order
    )

    start_time = None
    end_time = None
    for event in response['events']:
        if event['type'] == "TaskStateEntered" and event['stateEnteredEventDetails']['name'] == task_name:
            start_time = event['timestamp']
        elif event['type'] == "TaskStateExited" and event['stateExitedEventDetails']['name'] == task_name:
            end_time = event['timestamp']
        
        if start_time and end_time:
            return (end_time - start_time).total_seconds() / 60  # Convert to minutes

    return None  # Task not found

def calculate_average_runtime(environment, step_function_name, task_name):
    """Calculate average runtime of the task across executions."""
    try:
        step_function_arn = construct_step_function_arn(environment, step_function_name)
    except ValueError as e:
        print(str(e))
        return

    client = boto3.client('stepfunctions', region_name=AWS_REGION)
    executions = get_last_executions(client, step_function_arn)
    durations = []

    for exe_arn in executions:
        duration = get_task_durations(client, exe_arn, task_name)
        if duration is not None:
            durations.append(duration)

    if durations:
        avg_runtime = sum(durations) / len(durations)
        print(f"Average runtime of task '{task_name}' in '{environment}' environment over last {len(durations)} executions: {avg_runtime:.2f} minutes")
    else:
        print(f"No data found for task '{task_name}' in '{environment}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate average runtime of a task in AWS Step Functions.")

    parser.add_argument("--env", required=True, choices=ENV_ACCOUNT_MAP.keys(), help="Environment (internal-dev/internal-qa/dev/qa/sand/prod)")
    parser.add_argument("--step-function", required=True, help="Step function name", )
    parser.add_argument("--task", required=True, help="Task name")

    args = parser.parse_args()

    calculate_average_runtime(args.env, args.step_function, args.task)
