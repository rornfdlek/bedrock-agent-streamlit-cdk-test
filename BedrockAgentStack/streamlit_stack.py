from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
)
from constructs import Construct


class StreamlitStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        agent_id: str,
        agent_alias_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ───────── VPC & SG ─────────
        vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)

        sg = ec2.SecurityGroup(
            self, "StreamlitSg",
            vpc=vpc,
            description="Allow Streamlit",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8501), "Streamlit 8501")

        # ───────── IAM Role ─────────
        role = iam.Role(
            self, "StreamlitRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeAgent"], resources=["*"]))
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore")
        )

        # ───────── User Data ─────────
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            f'echo "export AGENT_ID={agent_id}" >> /etc/profile',
            f'echo "export AGENT_ALIAS_ID={agent_alias_id}" >> /etc/profile',
            f'echo "export AWS_REGION={self.region}" >> /etc/profile',

            "yum -y update",
            "yum -y install python3 python3-pip git",
            "python3 -m venv /home/ec2-user/venv",
            "source /home/ec2-user/venv/bin/activate",
            "pip install --upgrade pip",
            "pip install streamlit streamlit-chat boto3",
        )

        python_app = r'''import os, uuid, boto3, streamlit as st

AGENT_ID       = os.getenv("AGENT_ID")
AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")
REGION         = os.getenv("AWS_REGION")

client = boto3.client("bedrock-agent-runtime", region_name=REGION)

st.set_page_config(page_title="Bedrock Agent Chat", page_icon="🤖")
st.title("🦙 Bedrock Agent Chat — Streaming")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# 이전 대화 렌더링
for m in st.session_state["messages"]:
    st.chat_message(m["role"]).markdown(m["content"])

if prompt := st.chat_input("Say something"):
    st.session_state["messages"].append({"role": "user", "content": prompt})

    # 빈 placeholder 생성
    placeholder = st.chat_message("assistant").empty()
    collected   = []

    resp = client.invoke_agent(
        agentId      = AGENT_ID,
        agentAliasId = AGENT_ALIAS_ID,
        sessionId    = str(uuid.uuid4()),
        inputText    = prompt,
    )

    # EventStream 파싱
    for event in resp["completion"]:
        if "chunk" not in event:
            continue

        chunk = event["chunk"]
        if "content" in chunk:
            token = chunk["content"]
        elif "bytes" in chunk:
            token = chunk["bytes"].decode("utf-8")
        else:
            continue

        collected.append(token)
        placeholder.markdown("".join(collected))

    answer = "".join(collected)
    st.session_state["messages"].append(
        {"role": "assistant", "content": answer})
'''

        user_data.add_commands(
            'cat > /home/ec2-user/app.py << "PYEOF"',
            python_app,
            "PYEOF",
            "chown ec2-user:ec2-user /home/ec2-user/app.py",
            'su - ec2-user -c "bash -lc \''
            'source ~/venv/bin/activate && '
            'nohup streamlit run ~/app.py --server.port 8501 --server.headless true '
            '> ~/streamlit.log 2>&1 &\'"',
        )

        # ───────── EC2 ─────────
        instance = ec2.Instance(
            self, "StreamlitHost",
            vpc=vpc,
            security_group=sg,
            instance_type=ec2.InstanceType("t3.small"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=role,
            user_data=user_data,
        )

        CfnOutput(
            self, "StreamlitURL",
            value=f"http://{instance.instance_public_dns_name}:8501",
            description="Open after ~2‒3 min to chat with the agent",
        )