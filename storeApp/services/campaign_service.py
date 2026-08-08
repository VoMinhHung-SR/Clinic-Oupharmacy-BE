"""Campaign lifecycle service: status transitions + optimistic version lock."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from storeApp.models import Campaign
from storeApp.services.campaign_cache import (
    invalidate_public_campaign_cache,
    log_campaign_transition,
)

class CampaignServiceError(Exception):
    """Base error for campaign lifecycle operations."""


class CampaignVersionConflictError(CampaignServiceError):
    def __init__(self, *, expected_version, current_version):
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"Campaign version mismatch. expected={expected_version}, current={current_version}"
        )


class CampaignTransitionError(CampaignServiceError):
    def __init__(self, *, from_status, to_status, reason=None):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        msg = f"Illegal transition {from_status} → {to_status}"
        if reason:
            msg = f"{msg}: {reason}"
        super().__init__(msg)


# Legal edges from database.md (action helpers may add side effects).
ALLOWED_TRANSITIONS = {
    Campaign.STATUS_DRAFT: {
        Campaign.STATUS_SCHEDULED,
        Campaign.STATUS_ACTIVE,
        Campaign.STATUS_ARCHIVED,
    },
    Campaign.STATUS_SCHEDULED: {
        Campaign.STATUS_ACTIVE,
        Campaign.STATUS_DRAFT,
        Campaign.STATUS_ENDED,
        Campaign.STATUS_ARCHIVED,
    },
    Campaign.STATUS_ACTIVE: {
        Campaign.STATUS_PAUSED,
        Campaign.STATUS_ENDED,
    },
    Campaign.STATUS_PAUSED: {
        Campaign.STATUS_ACTIVE,
        Campaign.STATUS_ENDED,
    },
    Campaign.STATUS_ENDED: {
        Campaign.STATUS_ARCHIVED,
    },
    Campaign.STATUS_ARCHIVED: set(),
}


def _assert_version(*, campaign, expected_version):
    if expected_version is None:
        raise CampaignServiceError("expected_version is required")
    if campaign.version != expected_version:
        raise CampaignVersionConflictError(
            expected_version=expected_version,
            current_version=campaign.version,
        )


def _assert_transition(*, from_status, to_status):
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise CampaignTransitionError(from_status=from_status, to_status=to_status)


def _require_window_for_live(*, campaign, now):
    """schedule/publish require both ends; end_at must be strictly after start and in the future for go-live."""
    if campaign.start_at is None or campaign.end_at is None:
        raise CampaignServiceError("start_at and end_at are required")
    if campaign.end_at <= campaign.start_at:
        raise CampaignServiceError("end_at must be after start_at")
    if campaign.end_at <= now:
        raise CampaignServiceError("end_at must be in the future")


def _bump_and_save(*, campaign, update_fields, using):
    campaign.version = F("version") + 1
    fields = list(update_fields) + ["version", "updated_date"]
    campaign.save(using=using, update_fields=fields)
    campaign.refresh_from_db(using=using)
    return campaign


def _after_status_change(
    *,
    campaign,
    from_status,
    actor_user_id=None,
    source="api",
    invalidate=True,
):
    if from_status == campaign.status:
        return campaign
    log_campaign_transition(
        campaign_id=campaign.id,
        from_status=from_status,
        to_status=campaign.status,
        actor_user_id=actor_user_id,
        source=source,
    )
    if invalidate:
        invalidate_public_campaign_cache()
    return campaign


def get_campaign(*, campaign_id, using="store", for_update=False):
    qs = Campaign.objects.using(using)
    if for_update:
        qs = qs.select_for_update()
    return qs.get(id=campaign_id)


def transition_status(
    *,
    campaign_id,
    to_status,
    expected_version,
    using="store",
    actor_user_id=None,
    extra_updates=None,
):
    """Low-level transition with version check. Prefer named actions below."""
    with transaction.atomic(using=using):
        campaign = get_campaign(campaign_id=campaign_id, using=using, for_update=True)
        _assert_version(campaign=campaign, expected_version=expected_version)
        from_status = campaign.status
        _assert_transition(from_status=from_status, to_status=to_status)
        campaign.status = to_status
        update_fields = ["status"]
        if extra_updates:
            for key, value in extra_updates.items():
                setattr(campaign, key, value)
                update_fields.append(key)
        if actor_user_id is not None:
            campaign.updated_by_id = actor_user_id
            update_fields.append("updated_by_id")
        saved = _bump_and_save(campaign=campaign, update_fields=update_fields, using=using)
        return _after_status_change(
            campaign=saved,
            from_status=from_status,
            actor_user_id=actor_user_id,
            source="api",
        )


def schedule_campaign(*, campaign_id, expected_version, using="store", actor_user_id=None):
    """draft → scheduled (window required)."""
    with transaction.atomic(using=using):
        campaign = get_campaign(campaign_id=campaign_id, using=using, for_update=True)
        _assert_version(campaign=campaign, expected_version=expected_version)
        now = timezone.now()
        _require_window_for_live(campaign=campaign, now=now)
        from_status = campaign.status
        _assert_transition(from_status=from_status, to_status=Campaign.STATUS_SCHEDULED)
        campaign.status = Campaign.STATUS_SCHEDULED
        update_fields = ["status"]
        if actor_user_id is not None:
            campaign.updated_by_id = actor_user_id
            update_fields.append("updated_by_id")
        saved = _bump_and_save(campaign=campaign, update_fields=update_fields, using=using)
        return _after_status_change(
            campaign=saved,
            from_status=from_status,
            actor_user_id=actor_user_id,
            source="api",
        )


def publish_campaign(*, campaign_id, expected_version, using="store", actor_user_id=None):
    """
    publish_now: draft|scheduled → active.
    If start_at is null or in the future, set start_at=now (D-04). end_at must remain in the future.
    """
    with transaction.atomic(using=using):
        campaign = get_campaign(campaign_id=campaign_id, using=using, for_update=True)
        _assert_version(campaign=campaign, expected_version=expected_version)
        now = timezone.now()

        if campaign.end_at is None:
            raise CampaignServiceError("end_at is required to publish")
        if campaign.end_at <= now:
            raise CampaignServiceError("end_at must be in the future")

        start_at = campaign.start_at
        if start_at is None or start_at > now:
            start_at = now
        if campaign.end_at <= start_at:
            raise CampaignServiceError("end_at must be after start_at")

        from_status = campaign.status
        _assert_transition(from_status=from_status, to_status=Campaign.STATUS_ACTIVE)
        campaign.status = Campaign.STATUS_ACTIVE
        campaign.start_at = start_at
        update_fields = ["status", "start_at"]
        if actor_user_id is not None:
            campaign.updated_by_id = actor_user_id
            update_fields.append("updated_by_id")
        saved = _bump_and_save(campaign=campaign, update_fields=update_fields, using=using)
        return _after_status_change(
            campaign=saved,
            from_status=from_status,
            actor_user_id=actor_user_id,
            source="api",
        )


def pause_campaign(*, campaign_id, expected_version, using="store", actor_user_id=None):
    return transition_status(
        campaign_id=campaign_id,
        to_status=Campaign.STATUS_PAUSED,
        expected_version=expected_version,
        using=using,
        actor_user_id=actor_user_id,
    )


def resume_campaign(*, campaign_id, expected_version, using="store", actor_user_id=None):
    """paused → active if still in window; else force ended."""
    with transaction.atomic(using=using):
        campaign = get_campaign(campaign_id=campaign_id, using=using, for_update=True)
        _assert_version(campaign=campaign, expected_version=expected_version)
        from_status = campaign.status
        if from_status != Campaign.STATUS_PAUSED:
            raise CampaignTransitionError(
                from_status=from_status,
                to_status=Campaign.STATUS_ACTIVE,
                reason="resume only from paused",
            )
        now = timezone.now()
        if campaign.end_at is None or now >= campaign.end_at:
            campaign.status = Campaign.STATUS_ENDED
            update_fields = ["status"]
            if actor_user_id is not None:
                campaign.updated_by_id = actor_user_id
                update_fields.append("updated_by_id")
            saved = _bump_and_save(campaign=campaign, update_fields=update_fields, using=using)
            return _after_status_change(
                campaign=saved,
                from_status=from_status,
                actor_user_id=actor_user_id,
                source="api",
            )

        campaign.status = Campaign.STATUS_ACTIVE
        update_fields = ["status"]
        if actor_user_id is not None:
            campaign.updated_by_id = actor_user_id
            update_fields.append("updated_by_id")
        saved = _bump_and_save(campaign=campaign, update_fields=update_fields, using=using)
        return _after_status_change(
            campaign=saved,
            from_status=from_status,
            actor_user_id=actor_user_id,
            source="api",
        )


def end_campaign(*, campaign_id, expected_version, using="store", actor_user_id=None):
    return transition_status(
        campaign_id=campaign_id,
        to_status=Campaign.STATUS_ENDED,
        expected_version=expected_version,
        using=using,
        actor_user_id=actor_user_id,
    )


def archive_campaign(*, campaign_id, expected_version, using="store", actor_user_id=None):
    return transition_status(
        campaign_id=campaign_id,
        to_status=Campaign.STATUS_ARCHIVED,
        expected_version=expected_version,
        using=using,
        actor_user_id=actor_user_id,
    )


def unschedule_to_draft(*, campaign_id, expected_version, using="store", actor_user_id=None):
    """scheduled → draft."""
    return transition_status(
        campaign_id=campaign_id,
        to_status=Campaign.STATUS_DRAFT,
        expected_version=expected_version,
        using=using,
        actor_user_id=actor_user_id,
    )


def apply_time_expiry(*, campaign_id, using="store", now=None):
    """
    Scheduler helper: scheduled|active|paused → ended when now >= end_at.
    No version required (system clock). Returns campaign (possibly unchanged).
    """
    now = now or timezone.now()
    with transaction.atomic(using=using):
        campaign = get_campaign(campaign_id=campaign_id, using=using, for_update=True)
        from_status = campaign.status
        if from_status not in (
            Campaign.STATUS_SCHEDULED,
            Campaign.STATUS_ACTIVE,
            Campaign.STATUS_PAUSED,
        ):
            return campaign
        if campaign.end_at is None or now < campaign.end_at:
            return campaign
        campaign.status = Campaign.STATUS_ENDED
        saved = _bump_and_save(campaign=campaign, update_fields=["status"], using=using)
        return _after_status_change(
            campaign=saved,
            from_status=from_status,
            source="scheduler",
            invalidate=False,
        )


def activate_scheduled_campaign(*, campaign_id, using="store", now=None):
    """
    Scheduler helper: scheduled → active when start_at <= now < end_at.
    No-op if window missing or not yet/no longer valid.
    """
    now = now or timezone.now()
    with transaction.atomic(using=using):
        campaign = get_campaign(campaign_id=campaign_id, using=using, for_update=True)
        from_status = campaign.status
        if from_status != Campaign.STATUS_SCHEDULED:
            return campaign
        if campaign.start_at is None or campaign.end_at is None:
            return campaign
        if now < campaign.start_at or now >= campaign.end_at:
            return campaign
        campaign.status = Campaign.STATUS_ACTIVE
        saved = _bump_and_save(campaign=campaign, update_fields=["status"], using=using)
        return _after_status_change(
            campaign=saved,
            from_status=from_status,
            source="scheduler",
            invalidate=False,
        )


def run_campaign_scheduler(*, now=None, using="store"):
    """
    Converge statuses by clock (D-14):
    1) end scheduled|active|paused when now >= end_at
    2) activate scheduled when start_at <= now < end_at
    Idempotent. Public APIs still filter by window if cron is late.
    """
    now = now or timezone.now()
    stats = {"activated": 0, "ended": 0, "scanned_end": 0, "scanned_activate": 0}

    end_ids = list(
        Campaign.objects.using(using)
        .filter(
            status__in=[
                Campaign.STATUS_SCHEDULED,
                Campaign.STATUS_ACTIVE,
                Campaign.STATUS_PAUSED,
            ],
            end_at__isnull=False,
            end_at__lte=now,
        )
        .values_list("id", flat=True)
    )
    stats["scanned_end"] = len(end_ids)
    for campaign_id in end_ids:
        before = Campaign.objects.using(using).get(id=campaign_id).status
        after = apply_time_expiry(campaign_id=campaign_id, using=using, now=now)
        if before != Campaign.STATUS_ENDED and after.status == Campaign.STATUS_ENDED:
            stats["ended"] += 1

    activate_ids = list(
        Campaign.objects.using(using)
        .filter(
            status=Campaign.STATUS_SCHEDULED,
            start_at__isnull=False,
            end_at__isnull=False,
            start_at__lte=now,
            end_at__gt=now,
        )
        .values_list("id", flat=True)
    )
    stats["scanned_activate"] = len(activate_ids)
    for campaign_id in activate_ids:
        before = Campaign.objects.using(using).get(id=campaign_id).status
        after = activate_scheduled_campaign(campaign_id=campaign_id, using=using, now=now)
        if before == Campaign.STATUS_SCHEDULED and after.status == Campaign.STATUS_ACTIVE:
            stats["activated"] += 1

    if stats["activated"] or stats["ended"]:
        invalidate_public_campaign_cache()
    return stats


def resolve_attribution_campaign_id(raw_campaign_id, *, using="store"):
    """
    Best-effort attribution (D-10): accept existing campaign ids; ignore invalid/missing.
    Does not require public-active status — ended campaigns remain attributable.
    """
    if raw_campaign_id is None or raw_campaign_id == "":
        return None
    try:
        campaign_id = int(raw_campaign_id)
    except (TypeError, ValueError):
        return None
    if campaign_id <= 0:
        return None
    if Campaign.objects.using(using).filter(id=campaign_id).exists():
        return campaign_id
    return None
