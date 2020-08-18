from collections import defaultdict
from typing import TYPE_CHECKING, DefaultDict, Dict, List

import graphene
from django.core.exceptions import ValidationError
from django.db import transaction

from ....core.permissions import ShippingPermissions
from ....shipping.error_codes import ShippingErrorCode
from ....shipping.models import ShippingMethodChannelListing
from ...channel import ChannelContext
from ...channel.mutations import BaseChannelListing
from ...core.scalars import Decimal
from ...core.types.common import ShippingError
from ..types import ShippingMethod

if TYPE_CHECKING:
    from ....shipping.models import ShippingMethod as ShippingMethodModel

ErrorType = DefaultDict[str, List[ValidationError]]


class ShippingMethodChannelListingAddInput(graphene.InputObjectType):
    channel_id = graphene.ID(required=True, description="ID of a channel.")
    price = Decimal(
        description="Shipping price of the shipping method in this channel."
    )
    min_value = Decimal(
        description=(
            "Minimum order price to use this shipping method."
            "Note: this override original value of shipping method."
        )
    )
    max_value = Decimal(
        description=(
            "Maximum order price to use this shipping method."
            "Note: this override original value of shipping method."
        )
    )


class ShippingMethodChannelListingInput(graphene.InputObjectType):
    add_channels = graphene.List(
        graphene.NonNull(ShippingMethodChannelListingAddInput),
        description="List of channels to which the shipping method should be assigned.",
        required=False,
    )
    remove_channels = graphene.List(
        graphene.NonNull(graphene.ID),
        description=(
            "List of channels from which the shipping method should be unassigned."
        ),
        required=False,
    )


class ShippingMethodChannelListingUpdate(BaseChannelListing):
    shipping_method = graphene.Field(
        ShippingMethod, description="An updated shipping method instance."
    )

    class Arguments:
        id = graphene.ID(
            required=True, description="ID of a shipping method to update."
        )
        input = ShippingMethodChannelListingInput(
            required=True,
            description="Fields required to update shipping method channel listings.",
        )

    class Meta:
        description = "Manage shipping method's availability in channels."
        permissions = (ShippingPermissions.MANAGE_SHIPPING,)
        error_type_class = ShippingError
        error_type_field = "shipping_errors"

    @classmethod
    def add_channels(
        cls, shipping_method: "ShippingMethodModel", add_channels: List[Dict]
    ):
        for add_channel in add_channels:
            defaults = {
                "price": add_channel.get("price"),
                "min_value": add_channel.get("min_value", None),
                "max_value": add_channel.get("max_value", None),
            }
            ShippingMethodChannelListing.objects.update_or_create(
                shipping_method=shipping_method,
                channel=add_channel["channel"],
                defaults=defaults,
            )

    @classmethod
    def remove_channels(
        cls, shipping_method: "ShippingMethodModel", remove_channels: List[int]
    ):
        ShippingMethodChannelListing.objects.filter(
            shipping_method=shipping_method, channel_id__in=remove_channels
        ).delete()

    @classmethod
    @transaction.atomic()
    def save(cls, info, shipping_method: "ShippingMethodModel", cleaned_input: Dict):
        cls.add_channels(shipping_method, cleaned_input.get("add_channels", []))
        cls.remove_channels(shipping_method, cleaned_input.get("remove_channels", []))

    @classmethod
    def perform_mutation(cls, _root, info, id, input):
        shipping_method = cls.get_node_or_error(
            info, id, only_type=ShippingMethod, field="id"
        )
        errors = defaultdict(list)

        cleaned_input = cls.clean_channels(
            info, input, errors, ShippingErrorCode.DUPLICATED_INPUT_ITEM.value
        )
        if errors:
            raise ValidationError(errors)

        cls.save(info, shipping_method, cleaned_input)
        return ShippingMethodChannelListingUpdate(
            shipping_method=ChannelContext(node=shipping_method, channel_slug=None)
        )
