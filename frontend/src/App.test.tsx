import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";

test("muestra el título del sistema", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /control y registro de acceso/i }),
  ).toBeInTheDocument();
});
