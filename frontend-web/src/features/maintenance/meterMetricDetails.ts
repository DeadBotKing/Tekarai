import type { MeterService } from "./meterService";
import type { MeterReading } from "../../shared/types/domain";
import { metricDetail, type MetricDetails } from "../../shared/components/metricDetails";

/** Summary counters cover all readings, not only the 50 recent rows on screen. */
export async function loadMeterMetricDetails(meters: Pick<MeterService, "listReadings">, meterPointId: string,
  kind: "trusted" | "manual" | "sensor" | "suspect", signal?: AbortSignal): Promise<MetricDetails> {
  const rows: MeterReading[] = [];
  for (let page = 1; ; page++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const batch = await meters.listReadings({meterPointId, page, pageSize: 100,
      captureMode: kind === "manual" || kind === "sensor" ? kind : undefined,
      quality: kind === "suspect" ? "suspect" : undefined}, signal);
    rows.push(...batch);
    if (batch.length < 100) break;
  }
  const filtered = kind === "trusted" ? rows.filter(row => !row.supersededByReadingId && (row.quality === "good" || row.quality === "estimated")) : rows;
  return metricDetail(filtered, [["capturedAt", "تاریخ قرائت"], ["value", "مقدار"], ["delta", "مصرف"], ["unit", "واحد"], ["captureMode", "روش"], ["quality", "کیفیت"], ["recordedByName", "ثبت‌کننده"]],
    kind === "trusted" ? "مصرف کل، مجموع مصرف قرائت‌های معتبر و جایگزین‌نشده است؛ مانند محاسبهٔ خود گزارش." : "همهٔ قرائت‌های این گروه، شامل سوابق اصلاح‌شده؛ مطابق شمارندهٔ گزارش.");
}
