#!/usr/bin/env python3
"""Provision and tear down an OpenGRIS Scaler EC2 deployment.

Usage:
    python scripts/ec2-setup.py [OPTIONS]                 # provision
    python scripts/ec2-setup.py --destroy STATE.json      # tear down

Provision flow:
    1. Auto-discovers the latest AL2023 x86_64 AMI (or uses --ami-id).
    2. Creates an IAM role with an inline ORB policy and attaches it to a new
       instance profile, unless --instance-profile-name is given, in which case
       the existing profile is used and no IAM resources are created or deleted.
    3. Creates a uniquely-named key pair and writes the .pem to --key-file.
    4. Creates a security group that allows SSH, the scheduler port, and the
       object-storage port from your current public IP, plus all traffic from
       172.16.0.0/12 so ORB-provisioned workers can reach the scheduler over the
       VPC private network.
    5. Launches the instance with a user-data script that: fetches its own
       public and private IPs from the EC2 metadata service, installs uv and
       opengris-scaler, writes config.toml with the correct addresses, and starts
       scaler as a background process logging to /var/log/scaler.log.
    6. Polls the scheduler port via TCP until it accepts connections, controlled
       by --poll-timeout and --poll-interval.
    7. Prints a JSON state blob to stdout and optionally writes it to --state-file.

Destroy flow:
    --destroy STATE.json terminates the instance (waits for full termination),
    then deletes the security group, the key pair, and — if this script created
    the IAM stack — the instance profile, role, and inline policy.
    If provisioning failed partway through, the partial state printed to stderr
    (and written to --state-file if supplied) can be passed to --destroy for
    cleanup of whatever resources were created before the failure.

Key CLI options:
    --transport tcp|ws              Swaps tcp:// <-> ws:// throughout config.toml
                                    and in the reported scheduler/object-storage
                                    addresses.
    --worker-requirements PACKAGE   Repeatable. Passed as requirements_txt to the
                                    ORB worker manager, e.g.:
                                    --worker-requirements "opengris-scaler>=1.27.0"
                                    --worker-requirements numpy
    --worker-max-concurrency N      Total worker slots across all ORB instances.
    --suffix abc123                 Fixed resource-name suffix for reproducible
                                    runs; random 8-char alphanumeric by default.
    --instance-profile-name NAME    Skip IAM creation and use an existing profile.
"""

import argparse
import asyncio
import json
import random
import socket
import string
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import boto3
import websockets
from botocore.exceptions import ClientError

_EC2_TRUST_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
)

_ORB_INLINE_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:*",
                    "autoscaling:*",
                    "iam:GetRole",
                    "iam:PassRole",
                    "ssm:GetParameter",
                    "sts:GetCallerIdentity",
                ],
                "Resource": "*",
            }
        ],
    }
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProvisionConfig:
    region: str
    instance_type: str
    python_version: str
    scaler_package: str
    transport: str  # "tcp" or "ws"
    scheduler_port: int
    object_storage_port: int
    key_file: Path
    instance_profile_name: Optional[str]  # None → create one
    worker_instance_type: str
    worker_python_version: str
    worker_requirements: str
    worker_max_concurrency: Optional[int]
    poll_timeout: int
    poll_interval: int
    ami_id: Optional[str]  # None → auto-discover latest AL2023 x86_64
    name_suffix: str
    debug_dump_path: Optional[str] = None


@dataclass
class IAMState:
    instance_profile_name: str
    role_name: str  # empty string when not created by this script
    created: bool  # True → destroy must clean up this IAM stack


@dataclass
class ProvisionState:
    """Complete description of a provisioned deployment, sufficient for teardown."""

    region: str
    name_suffix: str
    instance_id: str
    key_pair_name: str
    key_file: str
    security_group_id: str
    public_ip: str
    private_ip: str
    transport: str
    scheduler_port: int
    object_storage_port: int
    scheduler_address: str
    object_storage_address: str
    iam: Optional[IAMState]
    worker_name: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProvisionState":
        """Lenient deserializer — missing fields default to empty/None so partial
        states saved after a failed provision can still be used with destroy()."""
        iam_raw = d.get("iam")
        iam = IAMState(**iam_raw) if iam_raw else None
        name_suffix = d.get("name_suffix", "")
        return cls(
            region=d.get("region", ""),
            name_suffix=name_suffix,
            instance_id=d.get("instance_id", ""),
            key_pair_name=d.get("key_pair_name", ""),
            key_file=d.get("key_file", ""),
            security_group_id=d.get("security_group_id", ""),
            public_ip=d.get("public_ip", ""),
            private_ip=d.get("private_ip", ""),
            transport=d.get("transport", "tcp"),
            scheduler_port=d.get("scheduler_port", 6788),
            object_storage_port=d.get("object_storage_port", 6789),
            scheduler_address=d.get("scheduler_address", ""),
            object_storage_address=d.get("object_storage_address", ""),
            iam=iam,
            worker_name=d.get("worker_name", f"scaler-worker-{name_suffix}"),
        )


class ProvisionError(Exception):
    """Raised when provisioning fails, carrying whatever partial state was collected."""

    def __init__(self, message: str, partial_state: dict) -> None:
        super().__init__(message)
        self.partial_state = partial_state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _random_suffix(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _my_public_ip() -> str:
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as resp:
        return resp.read().decode().strip()


def _latest_al2023_ami(ec2_client) -> str:
    resp = ec2_client.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-2023.*-kernel-*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )
    images = sorted(resp["Images"], key=lambda img: img["CreationDate"])
    if not images:
        raise RuntimeError("No AL2023 x86_64 AMI found in this region")
    return images[-1]["ImageId"]


def _git_pip_url(git_ref: str, extras: str = "[all]") -> str:
    """Convert 'owner/repo[@ref]' to a pip-installable PEP 440 git URL."""
    repo, _, ref = git_ref.partition("@")
    url = f"git+https://github.com/{repo}"
    if ref:
        url += f"@{ref}"
    return f"opengris-scaler{extras} @ {url}"


def _build_user_data(config: ProvisionConfig) -> str:
    """Return a bash user-data script that installs and starts scaler.

    Python-side values are substituted at call time via f-string.  Bash
    variable references use $VAR (no braces) so they don't conflict with the
    f-string syntax; they are expanded by bash at runtime when the heredoc is
    evaluated on the EC2 instance.
    """
    protocol = config.transport
    ws_slash = "/" if protocol == "ws" else ""
    sched_port = config.scheduler_port
    obj_port = config.object_storage_port

    concurrency_line = (
        f"\nmax_task_concurrency = {config.worker_max_concurrency}" if config.worker_max_concurrency is not None else ""
    )
    instance_tags_line = f'\ninstance_tags = {{Name = "scaler-worker-{config.name_suffix}"}}'
    debug_dump_path_line = (
        f'\ndebug_dump_path = "{config.debug_dump_path}"' if config.debug_dump_path is not None else ""
    )

    req_block = config.worker_requirements.strip()
    git_install_line = "dnf install -y git\n" if "git+" in config.scaler_package else ""

    # f'''...''' lets """ appear freely inside without ending the string.
    return f'''\
#!/bin/bash
set -euxo pipefail

IMDS_TOKEN=$(curl -sf -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
PUBLIC_IP=$(curl -sf -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
PRIVATE_IP=$(curl -sf -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)

export HOME=/root
{git_install_line}curl -LsSf https://astral.sh/uv/install.sh | sh
source /root/.local/bin/env

uv venv --python {config.python_version} /opt/scaler-venv
source /opt/scaler-venv/bin/activate
uv pip install \'{config.scaler_package}\'
uv pip install --upgrade orb-py

mkdir -p /opt/scaler

cat > /opt/scaler/config.toml << CONFIG_EOF
[object_storage_server]
bind_address = "{protocol}://0.0.0.0:{obj_port}{ws_slash}"

[scheduler]
bind_address = "{protocol}://0.0.0.0:{sched_port}{ws_slash}"
object_storage_address = "{protocol}://127.0.0.1:{obj_port}{ws_slash}"
advertised_object_storage_address = "{protocol}://$PUBLIC_IP:{obj_port}{ws_slash}"

[[worker_manager]]
type = "orb_aws_ec2"
scheduler_address = "{protocol}://127.0.0.1:{sched_port}{ws_slash}"
worker_manager_id = "wm-orb"
worker_scheduler_address = "{protocol}://$PRIVATE_IP:{sched_port}{ws_slash}"
object_storage_address = "{protocol}://$PRIVATE_IP:{obj_port}{ws_slash}"
python_version = "{config.worker_python_version}"
requirements_txt = """
{req_block}
"""
instance_type = "{config.worker_instance_type}"
aws_region = "{config.region}"
logging_level = "INFO"{concurrency_line}{instance_tags_line}{debug_dump_path_line}
CONFIG_EOF

/opt/scaler-venv/bin/scaler /opt/scaler/config.toml >> /var/log/scaler.log 2>&1 &
echo "Scaler started (PID=$!)"
'''


def _wait_for_tcp(host: str, port: int, timeout: int, interval: int) -> bool:
    """Poll host:port via raw TCP until a connection is accepted or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
    return False


def _wait_for_ws(url: str, timeout: int, interval: int) -> bool:
    """Poll a WebSocket URL until a connection is accepted or timeout elapses."""

    async def _probe() -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                async with websockets.connect(url, open_timeout=5):
                    return True
            except Exception:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(interval, remaining))
        return False

    return asyncio.run(_probe())


def _wait_for_scheduler(transport: str, host: str, port: int, timeout: int, interval: int) -> bool:
    if transport == "ws":
        return _wait_for_ws(f"ws://{host}:{port}/", timeout, interval)
    return _wait_for_tcp(host, port, timeout, interval)


def _create_iam_stack(iam_client, suffix: str) -> IAMState:
    role_name = f"scaler-ec2-role-{suffix}"
    profile_name = f"scaler-ec2-profile-{suffix}"

    print(f"Creating IAM role {role_name!r}...", file=sys.stderr)
    iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=_EC2_TRUST_POLICY,
        Description="OpenGRIS Scaler ORB worker manager role",
    )
    iam_client.put_role_policy(RoleName=role_name, PolicyName="ScalerORBPolicy", PolicyDocument=_ORB_INLINE_POLICY)

    try:
        print(f"Creating instance profile {profile_name!r}...", file=sys.stderr)
        iam_client.create_instance_profile(InstanceProfileName=profile_name)
        iam_client.add_role_to_instance_profile(InstanceProfileName=profile_name, RoleName=role_name)
    except Exception:
        # Roll back the role so we don't leave orphaned IAM resources.
        try:
            iam_client.delete_role_policy(RoleName=role_name, PolicyName="ScalerORBPolicy")
            iam_client.delete_role(RoleName=role_name)
        except Exception:
            pass
        raise

    # IAM propagation can take several seconds; without this sleep,
    # run_instances may fail with an InvalidParameterValue for the profile.
    print("Waiting for IAM instance profile to propagate...", file=sys.stderr)
    time.sleep(15)

    return IAMState(instance_profile_name=profile_name, role_name=role_name, created=True)


def _destroy_iam_stack(iam_client, iam: IAMState) -> None:
    if not iam.created:
        return

    print(f"Removing role from instance profile {iam.instance_profile_name!r}...", file=sys.stderr)
    _ignore_not_found(
        lambda: iam_client.remove_role_from_instance_profile(
            InstanceProfileName=iam.instance_profile_name, RoleName=iam.role_name
        )
    )

    print(f"Deleting instance profile {iam.instance_profile_name!r}...", file=sys.stderr)
    _ignore_not_found(lambda: iam_client.delete_instance_profile(InstanceProfileName=iam.instance_profile_name))

    print(f"Deleting role {iam.role_name!r}...", file=sys.stderr)
    try:
        for policy_name in iam_client.list_role_policies(RoleName=iam.role_name)["PolicyNames"]:
            iam_client.delete_role_policy(RoleName=iam.role_name, PolicyName=policy_name)
        iam_client.delete_role(RoleName=iam.role_name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise


def _ignore_not_found(fn) -> None:
    try:
        fn()
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def provision(config: ProvisionConfig, state_file: Optional[Path] = None) -> ProvisionState:
    """Provision an EC2 instance running OpenGRIS Scaler and return its state.

    All side effects (AWS resource creation, key file write) are performed here.
    Raises ProvisionError on failure, which carries the partial state dict so the
    caller can persist it for later cleanup.

    If state_file is given, the full state is written there as soon as all resource
    IDs and addresses are known — before waiting for the scheduler to come online.
    """
    session = boto3.Session(region_name=config.region)
    ec2 = session.client("ec2")
    iam_client = session.client("iam")

    suffix = config.name_suffix
    partial: dict = {"region": config.region, "name_suffix": suffix}

    try:
        # 1. Resolve AMI
        ami_id = config.ami_id or _latest_al2023_ami(ec2)
        print(f"Using AMI: {ami_id}", file=sys.stderr)

        # 2. IAM instance profile
        if config.instance_profile_name:
            iam_state = IAMState(instance_profile_name=config.instance_profile_name, role_name="", created=False)
        else:
            iam_state = _create_iam_stack(iam_client, suffix)
        partial["iam"] = asdict(iam_state)

        # 3. SSH key pair
        key_pair_name = f"scaler-key-{suffix}"
        print(f"Creating key pair {key_pair_name!r}...", file=sys.stderr)
        key_resp = ec2.create_key_pair(KeyName=key_pair_name)
        config.key_file.write_text(key_resp["KeyMaterial"])
        config.key_file.chmod(0o400)
        print(f"Key written to {config.key_file}", file=sys.stderr)
        partial["key_pair_name"] = key_pair_name
        partial["key_file"] = str(config.key_file)

        # 4. Security group
        my_ip = _my_public_ip()
        sg_name = f"scaler-sg-{suffix}"
        print(f"Creating security group {sg_name!r} (your IP: {my_ip})...", file=sys.stderr)
        sg_id = ec2.create_security_group(GroupName=sg_name, Description=f"OpenGRIS Scaler scheduler [{suffix}]")[
            "GroupId"
        ]
        partial["security_group_id"] = sg_id

        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": f"{my_ip}/32", "Description": "SSH from local machine"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": config.scheduler_port,
                    "ToPort": config.scheduler_port,
                    "IpRanges": [{"CidrIp": f"{my_ip}/32", "Description": "Scaler scheduler from local machine"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": config.object_storage_port,
                    "ToPort": config.object_storage_port,
                    "IpRanges": [{"CidrIp": f"{my_ip}/32", "Description": "Scaler object storage from local machine"}],
                },
                {
                    # All traffic from the RFC-1918 172.x range covering AWS default VPC
                    # subnets so ORB-provisioned workers can reach the scheduler.
                    "IpProtocol": "-1",
                    "IpRanges": [
                        {"CidrIp": "172.16.0.0/12", "Description": "All traffic from VPC private range (ORB workers)"}
                    ],
                },
            ],
        )

        # 5. Launch instance
        user_data = _build_user_data(config)
        print(f"Launching {config.instance_type} instance...", file=sys.stderr)
        run_resp = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=config.instance_type,
            KeyName=key_pair_name,
            SecurityGroupIds=[sg_id],
            IamInstanceProfile={"Name": iam_state.instance_profile_name},
            UserData=user_data,
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": f"scaler-scheduler-{suffix}"}]}
            ],
        )
        instance_id = run_resp["Instances"][0]["InstanceId"]
        partial["instance_id"] = instance_id
        print(f"Instance launched: {instance_id}", file=sys.stderr)

        # 6. Wait for running state
        print("Waiting for instance to reach running state...", file=sys.stderr)
        ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])

        desc = ec2.describe_instances(InstanceIds=[instance_id])
        inst = desc["Reservations"][0]["Instances"][0]
        public_ip = inst["PublicIpAddress"]
        private_ip = inst["PrivateIpAddress"]
        partial["public_ip"] = public_ip
        partial["private_ip"] = private_ip
        print(f"Public IP:  {public_ip}", file=sys.stderr)
        print(f"Private IP: {private_ip}", file=sys.stderr)

        # 7. Build client-facing addresses and persist state immediately
        ws_slash = "/" if config.transport == "ws" else ""
        scheduler_address = f"{config.transport}://{public_ip}:{config.scheduler_port}{ws_slash}"
        object_storage_address = f"{config.transport}://{public_ip}:{config.object_storage_port}{ws_slash}"
        partial.update(
            transport=config.transport,
            scheduler_port=config.scheduler_port,
            object_storage_port=config.object_storage_port,
            scheduler_address=scheduler_address,
            object_storage_address=object_storage_address,
        )

        state = ProvisionState(
            region=config.region,
            name_suffix=suffix,
            instance_id=instance_id,
            key_pair_name=key_pair_name,
            key_file=str(config.key_file),
            security_group_id=sg_id,
            public_ip=public_ip,
            private_ip=private_ip,
            transport=config.transport,
            scheduler_port=config.scheduler_port,
            object_storage_port=config.object_storage_port,
            scheduler_address=scheduler_address,
            object_storage_address=object_storage_address,
            iam=iam_state,
            worker_name=f"scaler-worker-{suffix}",
        )
        if state_file is not None:
            state_file.write_text(json.dumps(state.to_dict(), indent=2))
            print(f"State written to {state_file}", file=sys.stderr)

        # 8. Poll until the scheduler port accepts connections
        print(
            f"Waiting up to {config.poll_timeout}s for scheduler at {public_ip}:{config.scheduler_port}...",
            file=sys.stderr,
        )
        ready = _wait_for_scheduler(
            config.transport, public_ip, config.scheduler_port, config.poll_timeout, config.poll_interval
        )
        if not ready:
            raise RuntimeError(
                f"Scheduler did not become reachable within {config.poll_timeout}s. "
                "SSH into the instance and check /var/log/scaler.log for details."
            )
        print("Scheduler is reachable.", file=sys.stderr)

        return state

    except Exception as exc:
        raise ProvisionError(str(exc), partial) from exc


def destroy(state: ProvisionState) -> None:
    """Tear down all AWS resources described in state.

    Fields that are empty or None are skipped, so this also works with partial
    states saved after a failed provision.
    """
    session = boto3.Session(region_name=state.region)
    ec2 = session.client("ec2")
    iam_client = session.client("iam")

    # Terminate worker instances first (they hold the security group open).
    if state.worker_name:
        resp = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Name", "Values": [state.worker_name]},
                {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
            ]
        )
        worker_ids = [
            i["InstanceId"] for r in resp["Reservations"] for i in r["Instances"]
        ]
        if worker_ids:
            print(f"Terminating {len(worker_ids)} worker instance(s) ({state.worker_name})...", file=sys.stderr)
            try:
                ec2.terminate_instances(InstanceIds=worker_ids)
                ec2.get_waiter("instance_terminated").wait(InstanceIds=worker_ids)
                print("Worker instances terminated.", file=sys.stderr)
            except ClientError as exc:
                print(f"Warning: could not terminate worker instances: {exc}", file=sys.stderr)

    # Terminate scheduler instance so the security group is no longer in use.
    if state.instance_id:
        print(f"Terminating instance {state.instance_id}...", file=sys.stderr)
        try:
            ec2.terminate_instances(InstanceIds=[state.instance_id])
            print("Waiting for termination...", file=sys.stderr)
            ec2.get_waiter("instance_terminated").wait(InstanceIds=[state.instance_id])
            print("Instance terminated.", file=sys.stderr)
        except ClientError as exc:
            print(f"Warning: could not terminate instance: {exc}", file=sys.stderr)

    if state.security_group_id:
        print(f"Deleting security group {state.security_group_id}...", file=sys.stderr)
        try:
            ec2.delete_security_group(GroupId=state.security_group_id)
        except ClientError as exc:
            print(f"Warning: could not delete security group: {exc}", file=sys.stderr)

    if state.key_pair_name:
        print(f"Deleting key pair {state.key_pair_name!r}...", file=sys.stderr)
        try:
            ec2.delete_key_pair(KeyName=state.key_pair_name)
        except ClientError as exc:
            print(f"Warning: could not delete key pair: {exc}", file=sys.stderr)

    if state.iam:
        _destroy_iam_stack(iam_client, state.iam)

    print("Teardown complete.", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision or tear down an OpenGRIS Scaler EC2 deployment.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--destroy",
        metavar="STATE_JSON",
        help="Path to the JSON state file emitted by a previous provision run. "
        "Tears down all resources listed in the file.",
    )

    # AWS / scheduler instance
    aws = parser.add_argument_group("AWS / scheduler instance")
    aws.add_argument("--region", help="AWS region (default: boto3 session default)")
    aws.add_argument("--instance-type", default="c5.xlarge", help="Scheduler EC2 instance type")
    aws.add_argument("--ami-id", help="AMI ID override (default: latest AL2023 x86_64)")
    aws.add_argument(
        "--instance-profile-name",
        help="Existing IAM instance profile name to attach to the scheduler instance. "
        "If omitted, a new role and profile are created and destroyed on --destroy.",
    )

    # Scaler installation on the scheduler instance
    install = parser.add_argument_group("Scaler installation")
    install.add_argument(
        "--python-version", default="3.14", help="Python version to install on the scheduler instance via uv"
    )
    install.add_argument(
        "--scaler-package", default="opengris-scaler[all]", help="pip package spec for scaler on the scheduler instance"
    )
    install.add_argument(
        "--scaler-git",
        metavar="OWNER/REPO[@REF]",
        help="Install scaler from a GitHub repo/branch instead of PyPI "
        "(e.g. finos/opengris-scaler@my-branch). Mutually exclusive with --scaler-package. "
        "Also used as the default worker scaler requirement unless --worker-requirements is given.",
    )

    # Transport
    transport = parser.add_argument_group("Transport")
    transport.add_argument(
        "--transport",
        choices=["tcp", "ws"],
        default="tcp",
        help="Transport protocol for the scheduler and object storage",
    )
    transport.add_argument("--scheduler-port", type=int, default=6788)
    transport.add_argument("--object-storage-port", type=int, default=6789)

    # SSH key
    key = parser.add_argument_group("SSH key")
    key.add_argument("--key-file", help="Path to write the SSH private key (default: ./scaler-key-<suffix>.pem)")

    # ORB worker manager
    wm = parser.add_argument_group("ORB worker manager")
    wm.add_argument("--worker-instance-type", default="t3.medium", help="Worker EC2 instance type")
    wm.add_argument("--worker-python-version", default="3.14", help="Python version for workers")
    wm.add_argument(
        "--worker-requirements",
        action="append",
        dest="worker_requirements",
        metavar="PACKAGE",
        help="Package requirement for worker instances (repeat for multiple). " "Default: opengris-scaler[all]",
    )
    wm.add_argument(
        "--worker-max-concurrency",
        type=int,
        help="max_task_concurrency for the ORB worker manager "
        "(controls total number of worker slots across all instances)",
    )
    wm.add_argument(
        "--debug-dump-path",
        metavar="DIR",
        help="Directory on the scheduler instance where the ORB worker manager writes "
        "debug JSON dumps of its config and template (e.g. /tmp). Omit to disable.",
    )

    # Polling
    poll = parser.add_argument_group("Polling")
    poll.add_argument(
        "--poll-timeout", type=int, default=600, help="Seconds to wait for the scheduler port to become reachable"
    )
    poll.add_argument("--poll-interval", type=int, default=15, help="Seconds between port polls")

    # Output
    out = parser.add_argument_group("Output")
    out.add_argument(
        "--state-file",
        help="Write the JSON state to this file in addition to stdout. "
        "Pass this file to --destroy to tear down the deployment.",
    )
    out.add_argument(
        "--suffix",
        help="Name suffix for all AWS resources (default: random 8-char alphanumeric). "
        "Use a fixed suffix to make resource names predictable across runs.",
    )

    return parser


def main() -> None:
    parser = _build_cli()
    args = parser.parse_args()

    if args.destroy:
        state_path = Path(args.destroy)
        state = ProvisionState.from_dict(json.loads(state_path.read_text()))
        destroy(state)
        for path in [Path(state.key_file), state_path]:
            if path.exists():
                path.unlink()
                print(f"Deleted {path}", file=sys.stderr)
        return

    suffix = args.suffix or _random_suffix()
    key_file = Path(args.key_file) if args.key_file else Path(f"scaler-key-{suffix}.pem")
    state_file = Path(args.state_file) if args.state_file else Path(f"scaler-state-{suffix}.json")


    region = args.region or boto3.Session().region_name
    if not region:
        parser.error("Could not determine AWS region. Pass --region or configure the AWS CLI / environment.")

    if args.scaler_git and args.scaler_package != "opengris-scaler[all]":
        parser.error("--scaler-git and --scaler-package are mutually exclusive")

    if args.scaler_git:
        scaler_package = _git_pip_url(args.scaler_git)
        default_worker_req = _git_pip_url(args.scaler_git)
    else:
        scaler_package = args.scaler_package
        default_worker_req = "opengris-scaler[all]"

    worker_requirements = "\n".join(args.worker_requirements) if args.worker_requirements else default_worker_req

    config = ProvisionConfig(
        region=region,
        instance_type=args.instance_type,
        python_version=args.python_version,
        scaler_package=scaler_package,
        transport=args.transport,
        scheduler_port=args.scheduler_port,
        object_storage_port=args.object_storage_port,
        key_file=key_file,
        instance_profile_name=args.instance_profile_name,
        worker_instance_type=args.worker_instance_type,
        worker_python_version=args.worker_python_version,
        worker_requirements=worker_requirements,
        worker_max_concurrency=args.worker_max_concurrency,
        poll_timeout=args.poll_timeout,
        poll_interval=args.poll_interval,
        ami_id=args.ami_id,
        name_suffix=suffix,
        debug_dump_path=args.debug_dump_path,
    )

    try:
        state = provision(config, state_file=state_file)
        print(json.dumps(state.to_dict(), indent=2))
    except ProvisionError as exc:
        print(f"\nError during provisioning: {exc}", file=sys.stderr)
        if exc.partial_state:
            partial_output = json.dumps(exc.partial_state, indent=2)
            print("\nPartial state (pass to --destroy for cleanup):", file=sys.stderr)
            print(partial_output, file=sys.stderr)
            state_file.write_text(partial_output)
            print(f"\nPartial state written to {state_file}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
