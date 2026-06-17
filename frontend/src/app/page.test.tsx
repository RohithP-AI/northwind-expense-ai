import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { Employee, Submission } from "@/types";
import DashboardPage from "./page";

// Stub the router so the client component renders outside the Next app shell.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Mock only the network methods; keep the real ApiError so instanceof works.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listEmployees: vi.fn(),
      listSubmissions: vi.fn(),
    },
  };
});

import { api } from "@/lib/api";

const listEmployees = api.listEmployees as unknown as ReturnType<typeof vi.fn>;
const listSubmissions = api.listSubmissions as unknown as ReturnType<typeof vi.fn>;

const EMPLOYEE: Employee = {
  id: "11111111-1111-1111-1111-111111111111",
  employee_id: "NW-00001",
  name: "Ada Lovelace",
  grade: 5,
  title: "Engineer",
  department: "R&D",
  manager_id: null,
  home_base: "London",
  created_at: "2026-01-01T00:00:00Z",
};

const SUBMISSION: Submission = {
  id: "22222222-2222-2222-2222-222222222222",
  employee_id: "NW-00001",
  folder_name: "NW-00001_2026-06-01",
  trip_purpose: "Quarterly client review in Denver",
  trip_start_date: "2026-06-01",
  trip_end_date: "2026-06-03",
  status: "pending",
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("DashboardPage", () => {
  beforeEach(() => {
    listEmployees.mockReset();
    listSubmissions.mockReset();
  });

  it("renders the submissions table even when the employee request fails", async () => {
    listEmployees.mockRejectedValue(new ApiError("Employees down", 500));
    listSubmissions.mockResolvedValue([SUBMISSION]);

    render(<DashboardPage />);

    // The submissions table still renders with its data.
    expect(
      await screen.findByText(/quarterly client review in denver/i),
    ).toBeInTheDocument();
    // With no employee name map, the row falls back to the raw employee id.
    expect(screen.getAllByText("NW-00001").length).toBeGreaterThan(0);
    // No submissions error state, since the submissions request succeeded.
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument();
  });

  it("shows a disabled employee filter fallback when employees fail to load", async () => {
    listEmployees.mockRejectedValue(new ApiError("Employees down", 500));
    listSubmissions.mockResolvedValue([SUBMISSION]);

    render(<DashboardPage />);

    await screen.findByText(/quarterly client review in denver/i);

    const fallback = await screen.findByRole("option", {
      name: /employees unavailable/i,
    });
    const filter = fallback.closest("select") as HTMLSelectElement;
    expect(filter).toBeDisabled();
  });

  it("populates the employee filter when employees load successfully", async () => {
    listEmployees.mockResolvedValue([EMPLOYEE]);
    listSubmissions.mockResolvedValue([SUBMISSION]);

    render(<DashboardPage />);

    await screen.findByText(/quarterly client review in denver/i);

    const allEmployees = await screen.findByRole("option", {
      name: /all employees/i,
    });
    const filter = allEmployees.closest("select") as HTMLSelectElement;
    expect(filter).not.toBeDisabled();
    expect(
      screen.getByRole("option", { name: /ada lovelace \(nw-00001\)/i }),
    ).toBeInTheDocument();
  });

  it("shows the submissions error state when the submissions request fails", async () => {
    listEmployees.mockResolvedValue([EMPLOYEE]);
    listSubmissions.mockRejectedValue(new ApiError("Submissions down", 500));

    render(<DashboardPage />);

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText(/submissions down/i)).toBeInTheDocument();
    // The table is not shown when the submissions request fails.
    expect(
      screen.queryByText(/quarterly client review in denver/i),
    ).not.toBeInTheDocument();
  });
});
