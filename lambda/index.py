# lambda/index.py
import json
import os
import boto3
import re  # 正規表現モジュールをインポート
from botocore.exceptions import ClientError
import urllib.request # fastqpiリクエスト用に追加

# Lambda コンテキストからリージョンを抽出する関数
def extract_region_from_arn(arn):
    # ARN 形式: arn:aws:lambda:region:account-id:function:function-name
    match = re.search('arn:aws:lambda:([^:]+):', arn)
    if match:
        return match.group(1)
    return "us-east-1"  # デフォルト値

# グローバル変数としてクライアントを初期化（初期値）
bedrock_client = None

# モデルID
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")

# FASTAPIのURL
FASTAPI_URL = os.environ.get("https://dbca-34-13-141-15.ngrok-free.app/", "https://dbca-34-13-141-15.ngrok-free.app/")

def lambda_handler(event, context):
    try:
        # コンテキストから実行リージョンを取得し、クライアントを初期化
        global bedrock_client
        if bedrock_client is None:
            region = extract_region_from_arn(context.invoked_function_arn)
            bedrock_client = boto3.client('bedrock-runtime', region_name=region)
            print(f"Initialized Bedrock client in region: {region}")

        print("Received event:", json.dumps(event))

        # Cognitoで認証されたユーザー情報を取得
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")

        # リクエストボディの解析
        body = json.loads(event['body'])
        message = body['message']
        conversation_history = body.get('conversationHistory', [])

        print("Processing message:", message)
        print("Using model:", MODEL_ID)

        # 会話履歴を使用
        messages = conversation_history.copy()

        # ユーザーメッセージを追加
        messages.append({
            "role": "user",
            "content": message
        })

        ### 元のリクエストペイロード～API呼び出し～リクエスト解析
        # Nova Liteモデル用のリクエストペイロードを構築
        # 会話履歴を含める
        #bedrock_messages = []
        #for msg in messages:
        #    if msg["role"] == "user":
        #        bedrock_messages.append({
        #            "role": "user",
        #            "content": [{"text": msg["content"]}]
        #        })
        #    elif msg["role"] == "assistant":
        #        bedrock_messages.append({
        #            "role": "assistant", 
        #            "content": [{"text": msg["content"]}]
        #        })

        # invoke_model用のリクエストペイロード
        #request_payload = {
        #    "messages": bedrock_messages,
        #    "inferenceConfig": {
        #        "maxTokens": 512,
        #        "stopSequences": [],
        #        "temperature": 0.7,
        #        "topP": 0.9
        #    }
        #}

        #print("Calling Bedrock invoke_model API with payload:", json.dumps(request_payload))

        # invoke_model APIを呼び出し
        #response = bedrock_client.invoke_model(
        #    modelId=MODEL_ID,
        #    body=json.dumps(request_payload),
        #    contentType="application/json"
        #)

        # レスポンスを解析
        #response_body = json.loads(response['body'].read())
        #print("Bedrock response:", json.dumps(response_body, default=str))
        ### 上記まで元のリクエストペイロード～API呼び出し～レスポンス解析

        ###FastAPI用のリクエストペイロード～API呼び出し～レスポンス解析
        #FastAPI用リクエストペイロード
        request_payload = {
                "prompt": message,
                "max_new_tokens": 512,
                "do_sample":True,
                "temperature": 0.7,
                "top_p": 0.9
                }

        #FastAPI呼び出し
        req_data = json.dumps(request_payload).encode("utf-8")
        req = urllib.request.Request(
                f"{FASTAPI_URL}generate",
                data=req_data,
                headers={'Content-Type': 'application/json'},
                method='POST'
                )

        #fastqpiにリクエストを送信してレスポンス解析
        with urllib.request.urlopen(req) as res:
            response_body = json.loads(res.read())
        print("FsatAPI response:", json.dumps(response_body, default=str))
        ### 上記までFastAPI用のリクエストペイロード～API呼び出し～レスポンス

        # 応答の検証
        if not response_body.get('generated_text'): # 元のコード('output') or not response_body['output'].get('message') or not response_body['output']['message'].get('content'):
            raise Exception("No response content from the model")

        # アシスタントの応答を取得
        assistant_response = response_body['generated_text'] # 元のコード['output']['message']['content'][0]['text']

        # アシスタントの応答を会話履歴に追加
        messages.append({
            "role": "assistant",
            "content": assistant_response
        })

        # 成功レスポンスの返却
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
                "conversationHistory": messages
            })
        }

    except Exception as error:
        print("Error:", str(error))

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(error)
            })
        }