import os
import boto3

try:
    sqs_client = boto3.client(
        'sqs',
        region_name=os.environ['AWS_REGION'],
        endpoint_url=os.environ['SQS_ENDPOINT'],
        use_ssl=os.environ['USE_SSL'] == '1',
        verify=False,
        aws_access_key_id=os.environ['ACCESS_KEY'],
        aws_secret_access_key=os.environ['SECRET_KEY'])
except Exception as e:
    print(e)

queue_url = sqs_client.get_queue_url(QueueName=os.environ['SQS_QUEUE_NAME'])['QueueUrl']

try:
    # Receive message from SQS queue
    response = sqs_client.receive_message(
        QueueUrl=queue_url,
        AttributeNames=[
            'SentTimestamp'
        ],
        MaxNumberOfMessages=1,
        MessageAttributeNames=[
            'All'
        ],
        VisibilityTimeout=0,
        WaitTimeSeconds=0
    )
    print ("Response")
    print (response)
    print ('\n\n')
    message = response['Messages'][0]
    receipt_handle = message['ReceiptHandle']

    # Delete received message from queue
    sqs_client.delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=receipt_handle
    )
    print('Received message: %s' % message)

except Exception as e:
    print(e)