import type { components } from "./schema";
import { getClientId } from "./clientId";
import { send } from "./client";

type S = components["schemas"];
export type RecordKind = S["RecordCreate"]["kind"];
export type RecordSummary = S["RecordSummary"];
export type RecordDetail = S["RecordDetail"];
export type RecordList = S["RecordList"];
export type RecordsStatus = S["RecordsStatus"];

const headers = (extra: Record<string, string> = {}) => ({ "X-Client-Id": getClientId(), ...extra });
const JSON_TYPE = { "Content-Type": "application/json" };

export const getRecordsStatus = (signal?: AbortSignal) =>
  send<RecordsStatus>("/api/records/status", { method: "GET" }, signal);

export interface ListQuery { kind?: RecordKind; limit?: number; offset?: number }

export function listRecords(query: ListQuery = {}, signal?: AbortSignal) {
  const qs = new URLSearchParams();
  if (query.kind) qs.set("kind", query.kind);
  if (query.limit !== undefined) qs.set("limit", String(query.limit));
  if (query.offset !== undefined) qs.set("offset", String(query.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return send<RecordList>(`/api/records${suffix}`, { method: "GET", headers: headers() }, signal);
}

export const getRecord = (id: string, signal?: AbortSignal) =>
  send<RecordDetail>(`/api/records/${encodeURIComponent(id)}`, { method: "GET", headers: headers() }, signal);

export interface NewRecord {
  kind: RecordKind;
  title: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  app_version?: string;
}

export const createRecord = (record: NewRecord, signal?: AbortSignal) =>
  send<RecordDetail>(
    "/api/records",
    { method: "POST", headers: headers(JSON_TYPE), body: JSON.stringify(record) },
    signal,
  );

export const renameRecord = (id: string, title: string, signal?: AbortSignal) =>
  send<RecordSummary>(
    `/api/records/${encodeURIComponent(id)}`,
    { method: "PATCH", headers: headers(JSON_TYPE), body: JSON.stringify({ title }) },
    signal,
  );

export const deleteRecord = (id: string, signal?: AbortSignal) =>
  send<void>(`/api/records/${encodeURIComponent(id)}`, { method: "DELETE", headers: headers() }, signal);
