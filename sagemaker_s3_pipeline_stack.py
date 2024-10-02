from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_s3_notifications as s3_notifications,
    aws_sagemaker as sagemaker,
    aws_s3_assets as assets,  # Import assets for uploading files
    RemovalPolicy,
    Duration,
    Fn,
    CfnParameter
)
from constructs import Construct
import base64
import os

class SageMakerS3PipelineStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)


        # Define a parameter for the list
        custom_list_param = CfnParameter(self, "CustomList",
            type="CommaDelimitedList",
            description="A comma-separated list of values to be passed to the SageMaker notebook"
        )



        # S3 Bucket where the Excel file and processing script will be uploaded
        bucket = s3.Bucket(self, 
            "SFDCDataBucket",  # Added ID for the bucket
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # IAM Role for SageMaker Notebook Instance
        sagemaker_role = iam.Role(self, "SageMakerExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
        )

        # Attach S3 and Bedrock permissions to the SageMaker Role
        sagemaker_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            resources=[
                bucket.bucket_arn,
                bucket.arn_for_objects("*")
            ]
        ))

        sagemaker_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel"
            ],
            resources=["*"]  # Scope this to specific models if possible
        ))

        # Lambda function to trigger SageMaker notebook start
        lambda_fn = _lambda.Function(self, "SageMakerTriggerFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset(os.path.join(os.getcwd(), "lambda")),
            environment={
                "NOTEBOOK_INSTANCE_NAME": "SageMakerNotebookInstance",
                "BUCKET_NAME": bucket.bucket_name,
                "INPUT_FILE_NAME": "sfdc_test.xlsx",  # Update to match your file naming
            },
            timeout=Duration.minutes(5)
        )

        # Grant Lambda permissions to start/stop the SageMaker notebook instance
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["sagemaker:StartNotebookInstance", "sagemaker:StopNotebookInstance"],
            resources=["*"]  # You may scope this down to the specific notebook instance ARN
        ))

        # Grant Lambda access to the S3 bucket
        bucket.grant_read_write(lambda_fn)

        # Configure S3 event notification to trigger Lambda on file upload
        notification = s3_notifications.LambdaDestination(lambda_fn)
        bucket.add_event_notification(s3.EventType.OBJECT_CREATED, notification, s3.NotificationKeyFilter(suffix=".xlsx"))

        # Upload Python Notebook as an S3 asset
        notebook_asset = assets.Asset(self, "NotebookAsset",
            path=os.path.join(os.getcwd(), "notebooks/sfdccategorizer.ipynb")
        )

        # Grant read access to the asset for the SageMaker role
        notebook_asset.grant_read(sagemaker_role)

        # Define the notebook instance lifecycle configuration
        lifecycle_config = sagemaker.CfnNotebookInstanceLifecycleConfig(self, "NotebookLifecycleConfig",
            notebook_instance_lifecycle_config_name="SetupAndAutoStopLifecycleConfig",
            on_create=[sagemaker.CfnNotebookInstanceLifecycleConfig.NotebookInstanceLifecycleHookProperty(
                content=Fn.base64(Fn.sub(self.get_on_create_script(), {
                    "S3_NOTEBOOK_URL": notebook_asset.s3_object_url,
                    "BUCKET_NAME": bucket.bucket_name,
                    "CUSTOM_LIST": Fn.join(',',custom_list_param.value_as_list)
                }))
            )],
            on_start=[sagemaker.CfnNotebookInstanceLifecycleConfig.NotebookInstanceLifecycleHookProperty(
                content=Fn.base64(self.get_on_start_script())
            )]
        )

        # Define the notebook instance
        notebook_instance = sagemaker.CfnNotebookInstance(self, "SageMakerNotebookInstance",
            instance_type="ml.t2.medium",  # You can change this to a more powerful instance type if needed
            role_arn=sagemaker_role.role_arn,
            notebook_instance_name="SageMakerNotebookInstance",
            lifecycle_config_name=lifecycle_config.notebook_instance_lifecycle_config_name
        )

        # Output for visibility
        self.bucket = bucket
        self.lambda_fn = lambda_fn
        self.notebook_instance = notebook_instance

    def get_on_create_script(self):
        return """
        #!/bin/bash
        set -e
        LOG_FILE=/home/ec2-user/SageMaker/on_create.log
        echo "Starting SageMaker Lifecycle Configuration (On-Create)" >> $LOG_FILE

        # Download the Jupyter notebook from S3, log any errors
        echo "Downloading notebook from ${S3_NOTEBOOK_URL}" >> $LOG_FILE
        aws s3 cp ${S3_NOTEBOOK_URL} /home/ec2-user/SageMaker/sfdccategorizer.ipynb >> $LOG_FILE 2>&1
        echo "Notebook downloaded successfully" >> $LOG_FILE

        echo "On-Create Lifecycle Configuration complete" >> $LOG_FILE
        """
    
    def get_on_start_script(self):
        return """
        #!/bin/bash
        set -e
        LOG_FILE=/home/ec2-user/SageMaker/on_start.log
        echo "Starting SageMaker Lifecycle Configuration (On-Start)" >> $LOG_FILE

        # Create a file with the bucket name
        echo '${BUCKET_NAME}' > /home/ec2-user/SageMaker/bucket_name.txt
        echo "Bucket name saved to file" >> $LOG_FILE

        # Create a file with the custom list
        echo '${CUSTOM_LIST}' > /home/ec2-user/SageMaker/custom_list.txt
        echo "Custom list saved to file" >> $LOG_FILE

        # Set the Jupyter notebook to automatically shut down after 1 hour of inactivity
        IDLE_TIME=3600  # 1 hour
        echo "Setting up idle shutdown with IDLE_TIME=$IDLE_TIME" >> $LOG_FILE

        # Create a script to check for idle time and stop the notebook
        cat << EOF > /home/ec2-user/SageMaker/idle_checker.sh
        #!/bin/bash
        IDLE_TIME=$IDLE_TIME
        LAST_ACTIVITY=$(sudo find /home/ec2-user/SageMaker -name "*.ipynb" -mmin -$((IDLE_TIME/5)))
        if [ -z "$LAST_ACTIVITY" ]; then
            echo "No activity detected in the last $IDLE_TIME seconds. Stopping the notebook instance."
            sudo systemctl stop jupyter-server
        fi
        EOF

        chmod +x /home/ec2-user/SageMaker/idle_checker.sh

        # Create a cron job that will check idle time every 5 minutes
        echo "*/5 * * * * root /home/ec2-user/SageMaker/idle_checker.sh" > /etc/cron.d/auto-stop-sagemaker

        # Ensure the cron job file has the correct permissions
        chmod 0644 /etc/cron.d/auto-stop-sagemaker

        # Restart the cron service to apply changes
        systemctl restart cron

        echo "On-Start Lifecycle Configuration complete" >> $LOG_FILE
        """