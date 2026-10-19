import type { NormOp, NormStep } from "@/api/types";

export const NORMALIZATION_OPS: { op: NormOp; label: string }[] = [
  { op: "trim", label: "Recortar espacios" },
  { op: "upper", label: "Mayúsculas" },
  { op: "strip_leading_zeros", label: "Quitar ceros a la izquierda" },
  { op: "regex_extract", label: "Extraer con expresión regular" },
  { op: "hex_to_dec", label: "Hexadecimal a decimal" },
  { op: "dec_to_hex", label: "Decimal a hexadecimal" },
  { op: "pad_left", label: "Rellenar a la izquierda" },
];

export type StepDraft = {
  op: NormOp;
  pattern: string;
  length: number;
  char: string;
};

export function emptyStep(op: NormOp): StepDraft {
  return {
    op,
    pattern: op === "regex_extract" ? "(.+)" : "",
    length: op === "pad_left" ? 8 : 1,
    char: "0",
  };
}

export function draftFromStep(step: NormStep): StepDraft {
  return {
    op: step.op,
    pattern: step.pattern ?? "",
    length: step.length ?? 8,
    char: step.char ?? "0",
  };
}

export function stepFromDraft(draft: StepDraft): NormStep {
  if (draft.op === "regex_extract") {
    return { op: draft.op, pattern: draft.pattern };
  }
  if (draft.op === "pad_left") {
    return { op: draft.op, length: draft.length, char: draft.char || "0" };
  }
  return { op: draft.op };
}

export function opLabel(op: string): string {
  return NORMALIZATION_OPS.find((item) => item.op === op)?.label ?? op;
}
