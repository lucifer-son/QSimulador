import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getRecordsStatus, type RecordsStatus } from "../api/records";

export type HistoryAvailability = "checking" | "enabled" | "disabled";

interface RecordsContextValue {
  availability: HistoryAvailability;
  limits: Pick<RecordsStatus, "max_record_bytes" | "max_records_per_client"> | null;
  /** Leva o usuário à aba Histórico. */
  openHistory: () => void;
}

const RecordsContext = createContext<RecordsContextValue>({
  availability: "disabled", limits: null, openHistory: () => {},
});

export const useRecords = () => useContext(RecordsContext);

/** Pergunta uma vez à API se o histórico (PostgreSQL) está ativo neste servidor. */
export function RecordsProvider({ openHistory, children }: { openHistory: () => void; children: ReactNode }) {
  const [availability, setAvailability] = useState<HistoryAvailability>("checking");
  const [limits, setLimits] = useState<RecordsContextValue["limits"]>(null);

  useEffect(() => {
    const controller = new AbortController();
    getRecordsStatus(controller.signal)
      .then((status) => {
        if (controller.signal.aborted) return;
        setAvailability(status.enabled === true ? "enabled" : "disabled");
        setLimits({ max_record_bytes: status.max_record_bytes, max_records_per_client: status.max_records_per_client });
      })
      .catch(() => {
        if (!controller.signal.aborted) setAvailability("disabled");
      });
    return () => controller.abort();
  }, []);

  const value = useMemo(() => ({ availability, limits, openHistory }), [availability, limits, openHistory]);
  return <RecordsContext.Provider value={value}>{children}</RecordsContext.Provider>;
}
