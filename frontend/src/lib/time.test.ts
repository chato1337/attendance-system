import { expect, test } from "vitest";

import { fromDateTimeLocal, startOfDayIso, toDateTimeLocal } from "@/lib/time";

test("convierte la hora de Bogotá a UTC", () => {
  expect(fromDateTimeLocal("2026-10-18T14:30", "America/Bogota")).toBe("2026-10-18T19:30:00.000Z");
  expect(toDateTimeLocal("2026-10-18T19:30:00.000Z", "America/Bogota")).toBe("2026-10-18T14:30");
  expect(startOfDayIso("2026-10-18", "America/Bogota")).toBe("2026-10-18T05:00:00.000Z");
});
