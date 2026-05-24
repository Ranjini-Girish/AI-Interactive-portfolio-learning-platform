import { checkSrm } from "./srm.js";
import { cupedMean } from "./cuped.js";

export function buildReport(data) {
  const { config, assignments, exposures, conversions, covariates } = data;
  const experiments = config.experiments.map((exp) => {
    const weights = Object.fromEntries(exp.variants.map((v) => [v.variant_id, v.weight]));
    const observed = {};
    for (const v of exp.variants) observed[v.variant_id] = 0;
    for (const e of exposures) {
      if (e.experiment_id === exp.experiment_id) observed[e.variant_id]++;
    }
    const srm = checkSrm(observed, weights);
    const variants = exp.variants.map((v) => ({
      variant_id: v.variant_id,
      assigned: observed[v.variant_id],
      exposed: observed[v.variant_id],
      attributed_conversions: 0,
      converted: 0,
      conversion_rate: 0,
      cuped_rate: cupedMean([], covariates),
    }));
    return { experiment_id: exp.experiment_id, srm, variants, sequential_winners: [] };
  });
  return {
    metadata: {
      analysis_period: config.analysis_period,
      experiments_analyzed: experiments.length,
      attribution_rule: "first_touch",
      mutex_policy: "none",
    },
    experiments,
    mutex_violations: [],
  };
}
