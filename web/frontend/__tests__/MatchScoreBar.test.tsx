import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatchScoreBar } from "../components/MatchScoreBar";

describe("MatchScoreBar", () => {
  it("shows rounded percentage", () => {
    render(<MatchScoreBar score={73.6} />);
    expect(screen.getByText("74%")).toBeInTheDocument();
  });

  it("shows 0% for null score", () => {
    render(<MatchScoreBar score={null} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("uses green colour for scores ≥ 70", () => {
    const { container } = render(<MatchScoreBar score={70} />);
    expect(container.querySelector(".bg-green-500")).toBeTruthy();
  });

  it("uses amber colour for scores 40–69", () => {
    const { container } = render(<MatchScoreBar score={55} />);
    expect(container.querySelector(".bg-amber-400")).toBeTruthy();
  });

  it("uses red colour for scores < 40", () => {
    const { container } = render(<MatchScoreBar score={20} />);
    expect(container.querySelector(".bg-red-400")).toBeTruthy();
  });

  it("sets bar width to the score percentage", () => {
    const { container } = render(<MatchScoreBar score={60} />);
    const bar = container.querySelector<HTMLElement>(".bg-amber-400");
    expect(bar?.style.width).toBe("60%");
  });
});
