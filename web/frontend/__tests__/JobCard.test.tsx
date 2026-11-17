import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { JobCard } from "../components/JobCard";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    source: "smartrecruiters",
    title: "Senior Dev",
    company: "Talan",
    department: null,
    location: "Lima",
    remote: "remote",
    salary_min: null,
    salary_max: null,
    description: null,
    requirements: null,
    nice_to_haves: null,
    apply_url: null,
    posted_date: null,
    scraped_at: null,
    company_industry: null,
    match: null,
    ...overrides,
  };
}

describe("JobCard multi-location", () => {
  beforeEach(() => push.mockReset());

  it("shows no location toggle for a single posting", () => {
    render(<JobCard job={makeJob()} />);
    expect(screen.getByText("Lima")).toBeInTheDocument();
    expect(screen.queryByText(/\+\d+ location/)).toBeNull();
  });

  it("shows +N locations and expands to sibling links", () => {
    render(
      <JobCard
        job={makeJob({
          other_locations: [
            { id: 2, location: "Bogotá", country: "co" },
            { id: 3, location: null, country: "pe" },
          ],
        })}
      />
    );
    const toggle = screen.getByText("+2 locations");
    expect(screen.queryByText("Bogotá")).toBeNull();

    fireEvent.click(toggle);
    expect(screen.getByText("Bogotá")).toBeInTheDocument();
    expect(screen.getByText("PE")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Bogotá"));
    expect(push).toHaveBeenCalledWith("/jobs/2");
  });

  it("uses singular for one other location", () => {
    render(
      <JobCard
        job={makeJob({ other_locations: [{ id: 2, location: "Bogotá", country: "co" }] })}
      />
    );
    expect(screen.getByText("+1 location")).toBeInTheDocument();
  });
});
