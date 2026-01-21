from typing import Tuple

from scaler.scheduler.controllers.policies.scaling.fixed_elastic import FixedElasticScalingController
from scaler.scheduler.controllers.policies.scaling.mixins import ScalingController
from scaler.scheduler.controllers.policies.scaling.null import NullScalingController
from scaler.scheduler.controllers.policies.scaling.types import ScalingControllerStrategy
from scaler.scheduler.controllers.policies.scaling.vanilla import VanillaScalingController


def create_scaling_controller(
    scaling_controller_strategy: ScalingControllerStrategy, adapter_webhook_urls: Tuple[str, ...]
) -> ScalingController:
    if scaling_controller_strategy == ScalingControllerStrategy.NULL:
        return NullScalingController(*adapter_webhook_urls)
    elif scaling_controller_strategy == ScalingControllerStrategy.VANILLA:
        return VanillaScalingController(*adapter_webhook_urls)
    elif scaling_controller_strategy == ScalingControllerStrategy.FIXED_ELASTIC:
        return FixedElasticScalingController(*adapter_webhook_urls)

    raise ValueError(f"unsupported scaling controller strategy: {scaling_controller_strategy}")
