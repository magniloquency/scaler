import dataclasses
from typing import ClassVar, List, Optional

from scaler.config.common.logging import LoggingConfig
from scaler.config.common.worker import WorkerConfig
from scaler.config.common.worker_manager import WorkerManagerConfig
from scaler.config.config_class import ConfigClass


@dataclasses.dataclass
class ORBAWSEC2WorkerAdapterConfig(ConfigClass):
    """Configuration for the ORB AWS EC2 worker adapter."""

    _tag: ClassVar[str] = "orb_aws_ec2"

    worker_manager_config: WorkerManagerConfig

    # ORB AWS EC2 Template configuration
    image_id: Optional[str] = dataclasses.field(
        default=None,
        metadata=dict(
            help="AMI ID for the worker instances. If not provided, the latest AL2023 AMI is discovered automatically."
        ),
    )
    python_version: str = dataclasses.field(
        default="3.13", metadata=dict(help="Python version to install on the worker instance (e.g. '3.13')")
    )
    scaler_version: Optional[str] = dataclasses.field(
        default=None,
        metadata=dict(
            help="Version of opengris-scaler to install (e.g. '1.15.0'). Defaults to the latest version on PyPI."
        ),
    )
    key_name: Optional[str] = dataclasses.field(
        default=None, metadata=dict(help="AWS key pair name for the instances (optional)")
    )
    subnet_id: Optional[str] = dataclasses.field(
        default=None, metadata=dict(help="AWS subnet ID where the instances will be launched (optional)")
    )

    worker_config: WorkerConfig = dataclasses.field(default_factory=WorkerConfig)
    logging_config: LoggingConfig = dataclasses.field(default_factory=LoggingConfig)

    instance_type: str = dataclasses.field(default="t2.micro", metadata=dict(help="EC2 instance type"))
    aws_region: Optional[str] = dataclasses.field(default="us-east-1", metadata=dict(help="AWS region"))
    security_group_ids: List[str] = dataclasses.field(
        default_factory=list,
        metadata=dict(
            type=lambda s: [x for x in s.split(",") if x], help="Comma-separated list of AWS security group IDs"
        ),
    )
