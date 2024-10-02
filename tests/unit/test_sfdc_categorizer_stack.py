import aws_cdk as core
import aws_cdk.assertions as assertions

from sfdc_categorizer.sfdc_categorizer_stack import SfdcCategorizerStack

# example tests. To run these tests, uncomment this file along with the example
# resource in sfdc_categorizer/sfdc_categorizer_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = SfdcCategorizerStack(app, "sfdc-categorizer")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
