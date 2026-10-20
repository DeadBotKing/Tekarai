import type { PartLifecycleImpact, RepairScopeSuggestion } from "../../shared/types/domain";

export interface RepairScopeEvidence {
  title?: string;
  description?: string;
  failureSymptom?: string;
  rootCause?: string;
  actionTaken?: string;
  parts?: Array<{ name: string; lifecycleImpact?: PartLifecycleImpact }>;
}

const overhaulPhrases = ["اورهال", "بازسازی کامل", "تعمیر اساسی کامل", "full overhaul", "complete rebuild"];
const majorPhrases = [
  "تعمیر اساسی", "تعویض موتور", "تعویض گیربکس", "تعویض روتور", "تعویض استاتور",
  "تعویض شفت", "بازسازی موتور", "تعویض مجموعه پمپ", "major repair", "gearbox replacement",
  "motor replacement", "rotor replacement", "shaft replacement",
];
const minorPhrases = [
  "بلبرینگ", "یاتاقان", "فیلتر", "روغن کاری", "روانکاری", "تسمه", "واشر", "فیوز",
  "کاسه نمد", "bearing", "filter", "lubricant", "belt", "gasket", "fuse", "seal",
];

/** Local, explainable demo fallback. It returns a suggestion, never a decision. */
export function suggestRepairScopeLocally(evidence: RepairScopeEvidence): RepairScopeSuggestion {
  const text = [
    evidence.title,
    evidence.description,
    evidence.failureSymptom,
    evidence.rootCause,
    evidence.actionTaken,
  ].filter(Boolean).join(" ").toLocaleLowerCase();
  const parts = evidence.parts ?? [];
  const majorParts = parts.filter((part) => part.lifecycleImpact === "major");
  const minorParts = parts.filter((part) => part.lifecycleImpact === "minor");

  if (overhaulPhrases.some((phrase) => text.includes(phrase))) {
    return {
      suggestedScope: "overhaul",
      confidence: "high",
      reasons: ["شرح کار نشانهٔ صریح اورهال یا بازسازی کامل دارد."],
      requiresHumanConfirmation: true,
      analysisMethod: "demo-heuristic",
    };
  }
  if (majorPhrases.some((phrase) => text.includes(phrase))) {
    return {
      suggestedScope: "major",
      confidence: "high",
      reasons: ["شرح کار به تعمیر اساسی یا تعویض مجموعهٔ اصلی اشاره می‌کند."],
      requiresHumanConfirmation: true,
      analysisMethod: "demo-heuristic",
    };
  }
  if (majorParts.length) {
    return {
      suggestedScope: "major",
      confidence: "medium",
      reasons: [
        `قطعهٔ اصلی در سابقه ثبت شده: ${majorParts.slice(0, 4).map((part) => part.name).join("، ")}.`,
        "مصرف قطعه فقط قرینه است و تأیید تکنسین لازم است.",
      ],
      requiresHumanConfirmation: true,
      analysisMethod: "demo-heuristic",
    };
  }
  if (minorParts.length || minorPhrases.some((phrase) => text.includes(phrase))) {
    return {
      suggestedScope: "minor",
      confidence: "low",
      reasons: [
        "شواهد به بلبرینگ/یاتاقان یا قطعهٔ کوچک/مصرفی اشاره دارد.",
        "تعداد قطعات مصرفی به‌تنهایی تعمیر اساسی محسوب نمی‌شود.",
      ],
      requiresHumanConfirmation: true,
      analysisMethod: "demo-heuristic",
    };
  }
  return {
    suggestedScope: "unclassified",
    confidence: "low",
    reasons: [
      "شرح کار و طبقه‌بندی قطعات برای تشخیص شدت تعمیر شواهد کافی ندارند.",
      "تا تأیید تکنسین، رویداد تعمیر اساسی شمرده نمی‌شود.",
    ],
    requiresHumanConfirmation: true,
    analysisMethod: "demo-heuristic",
  };
}
