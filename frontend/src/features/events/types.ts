import type { components } from "@/lib/api-types";

type S = components["schemas"];
export type Event = S["EventOutput"];
export type EventSummary = S["EventSummary"];
export type EventPage = S["Page_EventSummary_"];
export type Round = S["RoundOutput"];
export type Track = S["TrackOutput"];
export type Prize = S["PrizeOutput"];
export type Team = S["TeamOutput"];
export type PublicTeam = S["PublicTeam"];
export type MyEvent = S["MyEvent"];
export type RoleItem = S["RoleOutput"];
export type Registration = S["Registration"];
export type Page<T> = { items: T[]; total: number };
