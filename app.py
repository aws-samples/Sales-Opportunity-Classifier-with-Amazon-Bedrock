#!/usr/bin/env python3

import aws_cdk as cdk
from sagemaker_s3_pipeline_stack import SageMakerS3PipelineStack

app = cdk.App()
SageMakerS3PipelineStack(app, "SageMakerS3PipelineStack")
app.synth()
