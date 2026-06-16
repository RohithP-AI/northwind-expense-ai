import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import PolicyAssistantPage from "./page";

// Mock only the network method; keep the real ApiError so instanceof checks work.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, policyAnswer: vi.fn() },
  };
});

import { api } from "@/lib/api";

const policyAnswer = api.policyAnswer as unknown as ReturnType<typeof vi.fn>;

async function ask(question: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/your question/i), question);
  await user.click(screen.getByRole("button", { name: /^ask$/i }));
  return user;
}

describe("PolicyAssistantPage", () => {
  beforeEach(() => {
    policyAnswer.mockReset();
  });

  it("shows a loading state while the answer is generated", async () => {
    // Never resolves during the test → loading stays visible.
    policyAnswer.mockReturnValue(new Promise(() => {}));
    render(<PolicyAssistantPage />);

    await ask("What is the meal limit?");

    expect(
      await screen.findByText(/reviewing the company policies/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /thinking/i })).toBeDisabled();
  });

  it("renders the answer in a single answer card", async () => {
    policyAnswer.mockResolvedValue({
      answer: "Employees can claim up to $75 per day for meals.",
      confidence: "high",
    });
    render(<PolicyAssistantPage />);

    await ask("What is the meal limit?");

    expect(
      await screen.findByText(/employees can claim up to \$75 per day/i),
    ).toBeInTheDocument();
    // No raw retrieval terminology leaks into the UI.
    expect(screen.queryByText(/similarity/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/results/i)).not.toBeInTheDocument();
  });

  it("renders the confidence badge", async () => {
    policyAnswer.mockResolvedValue({
      answer: "Yes, within the nightly hotel limit.",
      confidence: "medium",
    });
    render(<PolicyAssistantPage />);

    await ask("Hotel limit?");

    await screen.findByText(/within the nightly hotel limit/i);
    expect(screen.getByText(/confidence:/i)).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
  });

  it("renders an error state when the request fails", async () => {
    policyAnswer.mockRejectedValue(new ApiError("Internal error", 500));
    render(<PolicyAssistantPage />);

    await ask("What is the meal limit?");

    await waitFor(() =>
      expect(screen.getByText(/internal error/i)).toBeInTheDocument(),
    );
    // No answer card rendered on failure.
    expect(screen.queryByText(/confidence:/i)).not.toBeInTheDocument();
  });

  it("does not submit an empty question", async () => {
    render(<PolicyAssistantPage />);
    // Button is disabled with empty input.
    expect(screen.getByRole("button", { name: /^ask$/i })).toBeDisabled();
    expect(policyAnswer).not.toHaveBeenCalled();
  });
});
