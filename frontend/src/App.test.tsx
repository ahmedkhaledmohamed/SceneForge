import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import App from "./App";

test("renders the profile list shell", async () => {
  vi.stubGlobal("fetch", vi.fn(async () =>
    new Response(JSON.stringify([]), {
      headers: { "content-type": "application/json" },
    }),
  ));
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("Profiles")).toBeTruthy();
});
