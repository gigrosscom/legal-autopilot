"""«Доставить курьером» — the pilot «Курьер» (owner 01.10.2026, team/strategy/courier-delivery.md).

After the client paid for a document they order its delivery: the courier picks up two copies signed by the client,
hands them to the addressee against a signature on the second copy and brings the second copy back. The client pays
by a bill of its own (``invoices.purpose = "delivery"``, the same ways and the same Kaspi Pay push confirmation as
the document); once it is paid our system orders the courier (``providers.py``) and follows the order to the end.
The day of delivery starts the response deadline and its reminders.

Country data — price, cities, windows, provider codes, the client's texts — is in the pack's ``courier.yaml``.
"""

from .service import Courier, CourierConfig, config_of

__all__ = ["Courier", "CourierConfig", "config_of"]
