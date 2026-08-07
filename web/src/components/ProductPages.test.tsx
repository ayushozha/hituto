import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LandingPage, PricingPage } from "./ProductPages";

describe("commercial product pages", () => {
  it("presents the live teaching product and routes students into the tutor", () => {
    const html = renderToStaticMarkup(<LandingPage />);
    expect(html).toContain("Your SAT tutor that");
    expect(html).toContain("teaches out loud");
    expect(html).toContain('href="/app"');
    expect(html).toContain("Voice interruption");
  });

  it("describes beta access without claiming billing exists", () => {
    const html = renderToStaticMarkup(<PricingPage />);
    expect(html).toContain("$0");
    expect(html).toContain("no fake checkout");
    expect(html).toContain("Paid plans and limits will be published before billing is enabled");
  });
});
