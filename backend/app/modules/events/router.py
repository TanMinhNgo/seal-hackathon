from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencies import (
    EventServiceDependency,
    Limit,
    Offset,
    Search,
    TeamServiceDependency,
    no_store,
)
from app.core.schemas import Page
from app.modules.auth.dependencies import CurrentUser, OptionalUser, check_origin
from app.modules.auth.schemas import ErrorOutput, Role
from app.modules.events.schemas import (
    ArchiveInput,
    EventCreate,
    EventOutput,
    EventPatch,
    EventStatus,
    EventSummary,
    PrizeInput,
    PrizeOutput,
    PrizePatch,
    Registration,
    RoleInput,
    RoleOutput,
    RoundInput,
    RoundOutput,
    RoundPatch,
    TrackInput,
    TrackOutput,
    TrackPatch,
    TransitionInput,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["events"],
    dependencies=[Depends(check_origin), Depends(no_store)],
    responses={
        status: {"model": ErrorOutput} for status in (400, 401, 403, 404, 409, 422, 429, 503)
    },
)


@router.get("/events", response_model=Page[EventSummary], openapi_extra={"security": [{}]})
async def list_events(
    service: TeamServiceDependency,
    user: OptionalUser,
    status: EventStatus | None = None,
    q: Search = None,
    include_archived: bool = False,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[EventSummary]:
    return await service.list_events(user, status, q, include_archived, limit, offset)


@router.get("/events/by-slug/{slug}", response_model=EventOutput, openapi_extra={"security": [{}]})
async def event_slug(slug: str, service: EventServiceDependency, user: OptionalUser) -> EventOutput:
    return await service.by_slug(slug, user)


@router.get("/events/{event_id}", response_model=EventOutput, openapi_extra={"security": [{}]})
async def get_event(
    event_id: UUID, service: EventServiceDependency, user: OptionalUser
) -> EventOutput:
    return await service.read(event_id, user)


@router.post("/events", response_model=EventOutput, status_code=201)
async def create_event(
    data: EventCreate, service: EventServiceDependency, user: CurrentUser
) -> EventOutput:
    return await service.create(user, data)


@router.patch("/events/{event_id}", response_model=EventOutput)
async def update_event(
    event_id: UUID, data: EventPatch, service: TeamServiceDependency, user: CurrentUser
) -> EventOutput:
    return await service.update_event(user, event_id, data)


@router.post("/events/{event_id}/archive", response_model=EventOutput)
async def archive_event(
    event_id: UUID, data: ArchiveInput, service: EventServiceDependency, user: CurrentUser
) -> EventOutput:
    return await service.archive(user, event_id, data.archived)


@router.post("/events/{event_id}/transition", response_model=EventOutput)
async def transition_event(
    event_id: UUID, data: TransitionInput, service: TeamServiceDependency, user: CurrentUser
) -> EventOutput:
    return await service.transition(user, event_id, data.to_status)


@router.post("/events/{event_id}/register", status_code=201)
async def register_event(event_id: UUID, service: TeamServiceDependency, user: CurrentUser) -> None:
    await service.register(user, event_id)


@router.delete("/events/{event_id}/register", status_code=204)
async def withdraw_event(event_id: UUID, service: TeamServiceDependency, user: CurrentUser) -> None:
    await service.register(user, event_id, withdraw=True)


@router.get("/events/{event_id}/registrations", response_model=Page[Registration])
async def registrations(
    event_id: UUID,
    service: TeamServiceDependency,
    user: CurrentUser,
    q: Search = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[Registration]:
    return await service.registrations(user, event_id, q, limit, offset)


@router.get("/events/{event_id}/roles", response_model=Page[RoleOutput])
async def roles(
    event_id: UUID,
    service: EventServiceDependency,
    user: CurrentUser,
    role: Role | None = None,
    q: Search = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[RoleOutput]:
    return await service.role_list(user, event_id, role, q, limit, offset)


@router.post("/events/{event_id}/roles", response_model=RoleOutput, status_code=201)
async def grant_role(
    event_id: UUID, data: RoleInput, service: EventServiceDependency, user: CurrentUser
) -> RoleOutput:
    return await service.grant(user, event_id, data)


@router.delete("/events/{event_id}/roles/{role_id}", status_code=204)
async def revoke_role(
    event_id: UUID, role_id: UUID, service: EventServiceDependency, user: CurrentUser
) -> None:
    await service.revoke(user, event_id, role_id)


@router.get(
    "/events/{event_id}/rounds", response_model=Page[RoundOutput], openapi_extra={"security": [{}]}
)
async def rounds(
    event_id: UUID,
    service: EventServiceDependency,
    user: OptionalUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[RoundOutput]:
    rows, total = await service.child_list(user, event_id, "rounds", limit, offset)
    return Page(items=[RoundOutput.model_validate(row) for row in rows], total=total)


@router.post("/events/{event_id}/rounds", response_model=RoundOutput, status_code=201)
async def create_round(
    event_id: UUID, data: RoundInput, service: EventServiceDependency, user: CurrentUser
) -> RoundOutput:
    return RoundOutput.model_validate(await service.change_child(user, event_id, "rounds", data))


@router.patch("/events/{event_id}/rounds/{round_id}", response_model=RoundOutput)
async def update_round(
    event_id: UUID,
    round_id: UUID,
    data: RoundPatch,
    service: EventServiceDependency,
    user: CurrentUser,
) -> RoundOutput:
    return RoundOutput.model_validate(
        await service.change_child(user, event_id, "rounds", data, round_id)
    )


@router.delete("/events/{event_id}/rounds/{round_id}", status_code=204)
async def delete_round(
    event_id: UUID, round_id: UUID, service: EventServiceDependency, user: CurrentUser
) -> None:
    await service.change_child(user, event_id, "rounds", None, round_id)


@router.get(
    "/events/{event_id}/tracks", response_model=Page[TrackOutput], openapi_extra={"security": [{}]}
)
async def tracks(
    event_id: UUID,
    service: EventServiceDependency,
    user: OptionalUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[TrackOutput]:
    rows, total = await service.child_list(user, event_id, "tracks", limit, offset)
    return Page(items=[TrackOutput.model_validate(row) for row in rows], total=total)


@router.post("/events/{event_id}/tracks", response_model=TrackOutput, status_code=201)
async def create_track(
    event_id: UUID, data: TrackInput, service: EventServiceDependency, user: CurrentUser
) -> TrackOutput:
    return TrackOutput.model_validate(await service.change_child(user, event_id, "tracks", data))


@router.patch("/events/{event_id}/tracks/{track_id}", response_model=TrackOutput)
async def update_track(
    event_id: UUID,
    track_id: UUID,
    data: TrackPatch,
    service: EventServiceDependency,
    user: CurrentUser,
) -> TrackOutput:
    return TrackOutput.model_validate(
        await service.change_child(user, event_id, "tracks", data, track_id)
    )


@router.delete("/events/{event_id}/tracks/{track_id}", status_code=204)
async def delete_track(
    event_id: UUID, track_id: UUID, service: TeamServiceDependency, user: CurrentUser
) -> None:
    await service.delete_track(user, event_id, track_id)


@router.get(
    "/events/{event_id}/prizes", response_model=Page[PrizeOutput], openapi_extra={"security": [{}]}
)
async def prizes(
    event_id: UUID,
    service: EventServiceDependency,
    user: OptionalUser,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[PrizeOutput]:
    rows, total = await service.child_list(user, event_id, "prizes", limit, offset)
    return Page(items=[PrizeOutput.model_validate(row) for row in rows], total=total)


@router.post("/events/{event_id}/prizes", response_model=PrizeOutput, status_code=201)
async def create_prize(
    event_id: UUID, data: PrizeInput, service: EventServiceDependency, user: CurrentUser
) -> PrizeOutput:
    return PrizeOutput.model_validate(await service.change_child(user, event_id, "prizes", data))


@router.patch("/events/{event_id}/prizes/{prize_id}", response_model=PrizeOutput)
async def update_prize(
    event_id: UUID,
    prize_id: UUID,
    data: PrizePatch,
    service: EventServiceDependency,
    user: CurrentUser,
) -> PrizeOutput:
    return PrizeOutput.model_validate(
        await service.change_child(user, event_id, "prizes", data, prize_id)
    )


@router.delete("/events/{event_id}/prizes/{prize_id}", status_code=204)
async def delete_prize(
    event_id: UUID, prize_id: UUID, service: EventServiceDependency, user: CurrentUser
) -> None:
    await service.change_child(user, event_id, "prizes", None, prize_id)
