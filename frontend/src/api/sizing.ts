import type { components } from "./schema";
import { postJson } from "./client";
import type { Body } from "../domain/experiments";

type S = components["schemas"];

export type SizingTableResponse = S["SizingTableResponse"];
export type SizingSlaResponse = S["SizingSlaResponse"];
export type SizingCostResponse = S["SizingCostResponse"];
export type SizingRow = S["SizingRowOut"];
/** O que cada rota devolve; todas têm `rows`, `family`, `exact` e `warnings`. */
export type SizingResponse = SizingTableResponse | SizingSlaResponse | SizingCostResponse;

export const runSizingTable = (body: Body, signal?: AbortSignal) =>
  postJson<SizingTableResponse>("/api/sizing/table", body, signal);

export const runSizingSla = (body: Body, signal?: AbortSignal) =>
  postJson<SizingSlaResponse>("/api/sizing/sla", body, signal);

export const runSizingCost = (body: Body, signal?: AbortSignal) =>
  postJson<SizingCostResponse>("/api/sizing/cost", body, signal);
