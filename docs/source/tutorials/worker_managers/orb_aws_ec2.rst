ORB AWS EC2 Worker Manager
==========================

The ORB AWS EC2 worker manager allows Scaler to dynamically provision workers on AWS EC2 instances using the ORB (Open Resource Broker) system. This is particularly useful for scaling workloads that require significant compute resources or specialized hardware available in the cloud.

This tutorial describes the steps required to get up and running with the ORB AWS EC2 manager.

Requirements
------------

Before using the ORB AWS EC2 worker manager, ensure the following requirements are met on the machine that will run the manager:

1.  **orb-py and boto3**: The ``orb-py`` and ``boto3`` packages must be installed. These can be installed using the ``orb`` optional dependency of Scaler:

    .. code-block:: bash

        pip install "opengris-scaler[orb]"

2.  **AWS CLI**: The AWS Command Line Interface must be installed and configured with a default profile that has permissions to launch, describe, and terminate EC2 instances.

3.  **Network Connectivity**: The manager must be able to communicate with AWS APIs and the Scaler scheduler.

AWS Permissions
---------------

The AWS credentials used by the manager must have the following IAM permissions:

.. code-block:: json

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CancelSpotFleetRequests",
                    "ec2:CreateFleet",
                    "ec2:CreateKeyPair",
                    "ec2:CreateLaunchTemplate",
                    "ec2:CreateSecurityGroup",
                    "ec2:CreateTags",
                    "ec2:DeleteFleet",
                    "ec2:DeleteKeyPair",
                    "ec2:DeleteLaunchTemplate",
                    "ec2:DeleteNetworkInterface",
                    "ec2:DeleteSecurityGroup",
                    "ec2:DeleteVolume",
                    "ec2:DescribeFleets",
                    "ec2:DescribeImages",
                    "ec2:DescribeInstanceStatus",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceTypes",
                    "ec2:DescribeLaunchTemplates",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeSpotFleetInstances",
                    "ec2:DescribeSpotFleetRequests",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeVpcs",
                    "ec2:RequestSpotFleet",
                    "ec2:RunInstances",
                    "ec2:TerminateInstances",
                    "autoscaling:CreateAutoScalingGroup",
                    "autoscaling:CreateLaunchConfiguration",
                    "autoscaling:CreateOrUpdateTags",
                    "autoscaling:DeleteAutoScalingGroup",
                    "autoscaling:DeleteLaunchConfiguration",
                    "autoscaling:DescribeAutoScalingGroups",
                    "autoscaling:DescribeAutoScalingInstances",
                    "autoscaling:UpdateAutoScalingGroup",
                    "iam:GetRole",
                    "iam:PassRole",
                    "ssm:GetParameter",
                    "sts:GetCallerIdentity"
                ],
                "Resource": "*"
            }
        ]
    }

The EC2 and Auto Scaling permissions are used for provisioning and managing worker instances. ``iam:PassRole``
is required to associate an IAM role with launched instances. ``ssm:GetParameter`` is used to resolve AMI IDs
from the SSM Parameter Store. ``sts:GetCallerIdentity`` is used to validate credentials on startup.

.. note::
    If you do not intend to use Spot Fleet or Auto Scaling, you may omit the ``ec2:*SpotFleet*``,
    ``ec2:*Fleet*``, and ``autoscaling:*`` actions. The core permissions needed for basic on-demand
    instance provisioning are the ``ec2:Describe*``, ``ec2:RunInstances``, ``ec2:TerminateInstances``,
    ``ec2:CreateTags``, ``ec2:CreateLaunchTemplate``, ``ec2:DeleteLaunchTemplate``,
    ``ec2:CreateKeyPair``, ``ec2:DeleteKeyPair``, ``ec2:CreateSecurityGroup``,
    ``ec2:DeleteSecurityGroup``, ``iam:PassRole``, and ``sts:GetCallerIdentity`` permissions.

If you plan to use Spot Fleet, the ``AWSServiceRoleForEC2SpotFleet`` service-linked role must exist in your
account. If it does not, create it with:

.. code-block:: bash

    aws iam create-service-linked-role --aws-service-name spotfleet.amazonaws.com

Getting Started
---------------

To start the ORB AWS EC2 worker manager, use the ``scaler_worker_manager orb_aws_ec2`` subcommand:

.. code-block:: bash

    scaler_worker_manager orb_aws_ec2 tcp://<SCHEDULER_EXTERNAL_IP>:8516 \
        --object-storage-address tcp://<OSS_EXTERNAL_IP>:8517 \
        --instance-type t3.medium \
        --aws-region us-east-1 \
        --logging-level INFO \
        --task-timeout-seconds 60

Equivalent configuration using a TOML file with ``scaler``:

.. code-block:: toml

    # stack.toml

    [scheduler]
    scheduler_address = "tcp://<SCHEDULER_EXTERNAL_IP>:8516"

    [[worker_manager]]
    type = "orb_aws_ec2"
    scheduler_address = "tcp://<SCHEDULER_EXTERNAL_IP>:8516"
    object_storage_address = "tcp://<OSS_EXTERNAL_IP>:8517"
    # image_id = "ami-..."              # optional: pin a specific AMI (skips the install step)
    # python_version = "3.13"          # optional: Python version to install (default: 3.13)
    # scaler_version = "1.15.0"        # optional: pin scaler version (default: latest on PyPI)
    # requirements_file = "/path/to/requirements.txt"  # optional: custom deps; must include opengris-scaler
    instance_type = "t3.medium"
    aws_region = "us-east-1"
    logging_level = "INFO"
    task_timeout_seconds = 60

.. code-block:: bash

    scaler stack.toml

*   ``tcp://<SCHEDULER_EXTERNAL_IP>:8516`` is the address workers will use to connect to the scheduler.
*   ``tcp://<OSS_EXTERNAL_IP>:8517`` is the address workers will use to connect to the object storage server.
*   When ``--image-id`` is not provided, the adapter discovers the latest Amazon Linux 2023 AMI in the
    configured region and installs Python and ``opengris-scaler`` at instance startup via the EC2 user
    data script.
*   When ``--requirements-file`` is provided, the adapter installs packages from that file instead of
    installing ``opengris-scaler`` directly. ``opengris-scaler`` must be listed in the requirements file.

Networking Configuration
------------------------

Workers launched by the ORB AWS EC2 manager are EC2 instances and require an externally-reachable IP address for the scheduler.

*   **Internal Communication**: If the machine running the scheduler is another EC2 instance in the same VPC, you can use EC2 private IP addresses.
*   **Public Internet**: If communicating over the public internet, it is highly recommended to set up robust security rules and/or a VPN to protect the cluster.

Supported Parameters
--------------------

.. note::
    For more details on how to configure Scaler, see the :doc:`../commands` section.

The ORB AWS EC2 worker manager supports ORB-specific configuration parameters as well as common worker manager parameters.

ORB AWS EC2 Template Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*   ``--image-id``: AMI ID for the worker instances. If not provided, the latest Amazon Linux 2023 (AL2023)
    x86_64 HVM/EBS AMI in the configured region is discovered automatically.
*   ``--python-version``: Python version to install on each worker instance (default: ``3.13``). Only applies
    when ``--image-id`` is not specified.
*   ``--scaler-version``: Version of ``opengris-scaler`` to install (e.g. ``1.15.0``). Defaults to the latest
    available version on PyPI. Only applies when ``--image-id`` is not specified and ``--requirements-file`` is
    not provided.
*   ``--requirements-file``: Path to a ``requirements.txt`` file on the local machine. When provided, the file
    is embedded in the EC2 user data script and installed via ``pip install -r`` instead of installing
    ``opengris-scaler`` directly. ``opengris-scaler`` must be listed in the requirements file.
*   ``--instance-type``: EC2 instance type (default: ``t2.micro``).
*   ``--aws-region``: AWS region (default: ``us-east-1``).
*   ``--key-name``: AWS key pair name for the instances. If not provided, a temporary key pair will be created and deleted on cleanup.
*   ``--subnet-id``: AWS subnet ID where the instances will be launched. If not provided, it attempts to discover the default subnet in the default VPC.
*   ``--security-group-ids``: Comma-separated list of AWS security group IDs.

Common Parameters
~~~~~~~~~~~~~~~~~

For a full list of common parameters including networking, worker configuration, and logging, see :doc:`common_parameters`.

Cleanup
-------

The ORB AWS EC2 worker manager is designed to be self-cleaning, but it is important to be aware of the resources it manages:

*   **Key Pairs**: If a ``--key-name`` is not provided, the manager creates a temporary AWS key pair.
*   **Security Groups**: If ``--security-group-ids`` are not provided, the manager creates a temporary security group to allow communication.
*   **Launch Templates**: ORB may additionally create EC2 Launch Templates as part of the machine provisioning process.

The manager attempts to delete these temporary resources and terminate all launched EC2 instances when it shuts down gracefully. However, in the event of an ungraceful crash or network failure, some resources may persist in your AWS account.

.. tip::
    It is recommended to periodically check your AWS console for any orphaned resources (instances, security groups, key pairs, or launch templates) and clean them up manually if necessary to avoid unexpected costs.
