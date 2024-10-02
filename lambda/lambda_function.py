import boto3
import os

# Initialize the SageMaker client
sagemaker_client = boto3.client('sagemaker')

def lambda_handler(event, context):
    # Get the name of the SageMaker Notebook instance from the environment variables
    notebook_instance_name = os.environ['NOTEBOOK_INSTANCE_NAME']

    try:
        # Start the notebook instance
        print(f"Starting SageMaker Notebook instance: {notebook_instance_name}")
        response = sagemaker_client.start_notebook_instance(
            NotebookInstanceName=notebook_instance_name
        )
        print(f"Notebook instance {notebook_instance_name} has been started.")

        return {
            'statusCode': 200,
            'body': f"Notebook instance {notebook_instance_name} has been started."
        }

    except Exception as e:
        print(f"Error starting the notebook instance: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error starting the notebook instance: {str(e)}"
        }
