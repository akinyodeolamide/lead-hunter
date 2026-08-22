"""Delivery module for Lead Hunter."""
from lead_hunter.delivery.email_delivery import EmailDelivery
from lead_hunter.delivery.telegram_delivery import TelegramDelivery

__all__ = ["EmailDelivery", "TelegramDelivery"]
