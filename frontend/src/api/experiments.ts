import type { components } from "./schema";
import { postJson } from "./client";
import type { Body } from "../domain/experiments";

type S = components["schemas"];

export type SweepResponse = S["SweepResponse"];
export type SweepPoint = S["SweepPointOut"];
export type ServerComparisonResponse = S["ServerComparisonResponse"];
export type SensitivityResponse = S["SensitivityResponse"];
export type ParameterSensitivity = S["ParameterSensitivityOut"];

export const runSweep = (body: Body, signal?: AbortSignal) =>
  postJson<SweepResponse>("/api/experiments/sweep", body, signal);

export const runServerComparison = (body: Body, signal?: AbortSignal) =>
  postJson<ServerComparisonResponse>("/api/experiments/servers", body, signal);

export const runSensitivity = (body: Body, signal?: AbortSignal) =>
  postJson<SensitivityResponse>("/api/experiments/sensitivity", body, signal);
