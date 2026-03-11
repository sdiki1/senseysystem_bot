from enum import Enum


class UserStage(str, Enum):
    NEW = "new"
    DIAGNOSTIC_IN_PROGRESS = "diagnostic_in_progress"
    DIAGNOSTIC_RESULT = "diagnostic_result"
    OFFER_CLUB = "offer_club"
    OFFER_CONSULT = "offer_consult"
    PAYMENT_CLUB = "payment_club"
    PAYMENT_CONSULT = "payment_consult"
    CLUB_ACTIVE = "club_active"
    CONSULT_BOOKED = "consult_booked"


class ProductType(str, Enum):
    CLUB = "club"
    CONSULT = "consult"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"


class ReminderKind(str, Enum):
    DIAG_15M = "diag_15m"
    DIAG_2H = "diag_2h"
    DIAG_12H = "diag_12h"

    RESULT_12H = "result_12h"
    RESULT_24H = "result_24h"
    RESULT_72H = "result_72h"
    RESULT_7D = "result_7d"

    PAYMENT_CLUB_20M = "payment_club_20m"
    PAYMENT_CLUB_3H = "payment_club_3h"

    PAYMENT_CONSULT_20M = "payment_consult_20m"
    PAYMENT_CONSULT_3H = "payment_consult_3h"

    POST_CLUB_24H = "post_club_24h"


class ReminderStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class BroadcastContentType(str, Enum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"


class BroadcastTarget(str, Enum):
    ALL = "all"
    CLUB = "club"
    CONSULT = "consult"
