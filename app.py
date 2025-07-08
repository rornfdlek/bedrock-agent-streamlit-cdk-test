#!/usr/bin/env python3
import os
import json
import aws_cdk as cdk

from BedrockAgentStack.BedrockAgentStack_stack import BedrockAgentStack
from BedrockAgentStack.streamlit_stack import StreamlitStack


app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region =os.getenv("CDK_DEFAULT_REGION"),
)

# ① Bedrock Agent 스택 (기존 파일, 여기서 Agent ID 출력 필요)
agent_stack = BedrockAgentStack(app, "BedrockAgentStack", env=env)

# ② Streamlit UI 스택 – Agent ID/별칭 전달
StreamlitStack(
    app,
    "StreamlitChatStack",
    env=env,
    agent_id=agent_stack.agent_id_output.value,
    agent_alias_id=agent_stack.agent_alias_id_output.value,
)


app.synth()
