import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../core/api/apiClient";
import {
  createMaintenanceService,
  type RepairScopeSuggestionInput,
} from "../features/maintenance/maintenanceService";
import { suggestRepairScopeLocally } from "../features/maintenance/repairScopeSuggestion";

const apiStub = (): ApiClient & { post: ReturnType<typeof vi.fn> } =>
  ({ post: vi.fn().mockResolvedValue({}) }) as unknown as ApiClient & { post: ReturnType<typeof vi.fn> };

describe("repair-scope suggestions", () => {
  it("treats bearings and consumables as minor and never confirms on its own", () => {
    const suggestion = suggestRepairScopeLocally({
      title: "Replace bearing",
      actionTaken: "بلبرینگ و فیلتر تعویض شد",
      parts: [{ name: "bearing 6204", lifecycleImpact: "minor" }],
    });

    expect(suggestion.suggestedScope).toBe("minor");
    expect(suggestion.requiresHumanConfirmation).toBe(true);
    expect(suggestion.reasons.join(" ")).toMatch(/تعداد قطعات مصرفی/);
  });

  it("keeps ambiguous descriptions unclassified", () => {
    const suggestion = suggestRepairScopeLocally({ description: "Noise inspected; no repair details" });

    expect(suggestion.suggestedScope).toBe("unclassified");
    expect(suggestion.requiresHumanConfirmation).toBe(true);
  });

  it("routes production suggestions through the server API", async () => {
    const api = apiStub();
    const service = createMaintenanceService(api);
    const input: RepairScopeSuggestionInput = {
      title: "Pump",
      failureSymptom: "Low flow",
      actionTaken: "Replaced impeller",
    };

    await service.suggestRepairScope("wo-1", input);

    expect(api.post).toHaveBeenCalledWith(
      expect.stringContaining("repair-scope-suggestion"),
      { failureSymptom: "Low flow", rootCause: "", actionTaken: "Replaced impeller" },
      expect.objectContaining({ retry: 0 }),
    );
  });

  it("uses the local demo advisor through the same service method", async () => {
    const api = apiStub();
    const service = createMaintenanceService(api, suggestRepairScopeLocally);

    const suggestion = await service.suggestRepairScope("wo-2", {
      title: "Bearing replacement",
    });

    expect(suggestion.suggestedScope).toBe("minor");
    expect(suggestion.requiresHumanConfirmation).toBe(true);
    expect(api.post).not.toHaveBeenCalled();
  });
});
