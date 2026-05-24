import { readFileSync } from "fs";
export function loadData() {
  return {
    config: JSON.parse(readFileSync("/app/config/experiments.json", "utf-8")),
    calendar: JSON.parse(readFileSync("/app/config/calendar.json", "utf-8")),
    boundaries: JSON.parse(readFileSync("/app/config/boundaries.json", "utf-8")),
    assignments: JSON.parse(readFileSync("/app/data/assignments.json", "utf-8")),
    exposures: JSON.parse(readFileSync("/app/data/exposures.json", "utf-8")),
    conversions: JSON.parse(readFileSync("/app/data/conversions.json", "utf-8")),
    covariates: JSON.parse(readFileSync("/app/data/covariates.json", "utf-8")),
  };
}
