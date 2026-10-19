import axios from "axios";
import { expect, test } from "vitest";

import { canAdminister, canOperate, slugify } from "@/lib/access";
import { errorMessage } from "@/lib/errors";

test("el operador modifica el dominio y el administrador también los nodos", () => {
  expect(canOperate("OPERATOR")).toBe(true);
  expect(canAdminister("OPERATOR")).toBe(false);
  expect(canAdminister("ADMIN")).toBe(true);
  expect(canOperate("VIEWER")).toBe(false);
  expect(slugify("Sede Norte")).toBe("sede-norte");
});

test("traduce el detalle de un error de la API", () => {
  const error = new axios.AxiosError("falló");
  error.response = {
    data: { detail: "Duplicado" },
    status: 400,
    statusText: "Bad Request",
    headers: {},
    config: { headers: new axios.AxiosHeaders() },
  };
  expect(errorMessage(error)).toBe("Duplicado");
});
