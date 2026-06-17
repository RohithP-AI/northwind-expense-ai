import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Nav } from "./Nav";

// Nav reads the current path to highlight the active link.
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("Nav", () => {
  it("labels the policy link 'Policy Assistant' and points it at /policy", () => {
    render(<Nav />);

    const link = screen.getByRole("link", { name: "Policy Assistant" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/policy");

    // The old "Policy Search" label is gone.
    expect(
      screen.queryByRole("link", { name: /policy search/i }),
    ).not.toBeInTheDocument();
  });
});
